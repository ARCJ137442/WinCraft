"""Acceptance probe against the REAL Rust host; no Python model substitutes for it.

- 🤖Covers authorization, lease expiry, disconnect/reconnect fencing, and slow consumers.
"""
from __future__ import annotations

import argparse
import asyncio
import http.client
import json
import uuid
from typing import Any
from urllib.parse import urlparse

from websockets.exceptions import ConnectionClosed

from client import Client, RpcError, add_runtime_args, require_runtime


LEASE_EXPIRY_GRACE_SECONDS: float = 0.75
'''租约过期后的 housekeeping 等待余量'''

SLOW_PAYLOAD_BYTES: int = 32 * 1024
'''真实慢消费者测试中每个快照的数据大小'''

SLOW_BURST_COUNT: int = 1024
'''超过服务端有限广播队列容量的真实快照数量'''

SLOW_REQUEST_INTERVAL_SECONDS: float = 0.02
'''慢消费者负载的最小请求间隔，低于服务端每秒请求上限'''

SLOW_READER_TIMEOUT_SECONDS: float = 20.0
'''等待服务端要求重同步或断开慢消费者的最长时间'''


async def expect_code(
    client: Client,
    method: str,
    params: dict[str, Any],
    code: str,
) -> None:
    '''断言真实服务端返回指定协议错误。
    - 🎯让拒绝路径在探针输出中成为显式验收项
    '''
    try:
        await client.call(method, params)
    except RpcError as error:
        assert error.code == code, (error.code, code)
        return
    raise AssertionError(f'Expected rejection: {code}')


async def check_positive_scene_patches(
    client: Client, world_id: str, lease: dict[str, Any]
) -> None:
    """Exercise all live structural patch operations against the real server."""
    initial = await client.mutate(
        'scene.replace',
        world_id,
        lease,
        scene={
            'root': {
                'id': 'root',
                'kind': 'stack',
                'children': [
                    {
                        'id': 'a',
                        'kind': 'text',
                        'props': {'text': 'before'},
                        'children': [],
                    },
                    {
                        'id': 'b',
                        'kind': 'badge',
                        'props': {'text': 'replace target'},
                        'children': [],
                    },
                    {'id': 'c', 'kind': 'divider', 'children': []},
                ],
            },
            'data': {},
        },
    )
    patched = await client.mutate(
        'scene.patch',
        world_id,
        lease,
        ops=[
            {
                'op': 'insert',
                'parent': 'root',
                'index': 3,
                'node': {
                    'id': 'd',
                    'kind': 'text',
                    'props': {'text': 'temporary'},
                    'children': [],
                },
            },
            {'op': 'move', 'node_id': 'c', 'parent': 'root', 'index': 0},
            {
                'op': 'replace',
                'node_id': 'b',
                'node': {
                    'id': 'b2',
                    'kind': 'text',
                    'props': {'text': 'replaced'},
                    'children': [],
                },
            },
            {'op': 'props', 'node_id': 'a', 'props': {'text': 'patched'}},
            {'op': 'remove', 'node_id': 'd'},
        ],
    )

    children = patched['scene']['root']['children']
    assert [node['id'] for node in children] == ['c', 'a', 'b2']
    by_id = {node['id']: node for node in children}
    assert by_id['a']['props']['text'] == 'patched'
    assert by_id['b2']['props']['text'] == 'replaced'
    assert patched['revision'] == initial['revision'] + 1


async def check_legacy_protocol_rejected(client: Client) -> None:
    """The previous wire version must fail its hello instead of being coerced."""
    from websockets.asyncio.client import connect

    socket = await connect(
        client.url,
        additional_headers={
            'Authorization': f"Bearer {client.descriptor['token']}"
        },
        open_timeout=5,
        ping_interval=None,
    )
    try:
        try:
            await raw_call(
                socket,
                'hello',
                {'protocol': '0.2', 'provider_name': 'probe.legacy-version'},
            )
        except RpcError as error:
            assert error.code == 'PROTOCOL_MISMATCH', error.code
        else:
            raise AssertionError('The previous protocol version unexpectedly connected')
    finally:
        await socket.close()


async def wait_for_native_window_revision(
    client: Client, world_id: str, expected_revision: int
) -> dict[str, Any]:
    """Wait for the real native adapter when present; headless checks model state only."""
    native_windows = bool(client.ready.get('capabilities', {}).get('native_windows'))
    deadline = asyncio.get_running_loop().time() + 5.0
    while True:
        snapshot = await client.call('world.snapshot', {'world_id': world_id})
        native = snapshot['native']
        if snapshot['window_revision'] >= expected_revision and (
            not native_windows
            or (
                native['state'] == 'applied'
                and native['applied_window_revision'] == snapshot['window_revision']
            )
        ):
            return snapshot
        if native['state'] == 'error' or asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(
                'native window configuration was not applied: '
                f"expected_revision={expected_revision}; "
                f"actual_revision={snapshot['window_revision']}; "
                f"state={native['state']}; "
                f"applied_revision={native['applied_window_revision']}; "
                f"error_present={bool(native['error'])}"
            )
        await asyncio.sleep(0.05)


async def wait_for_window_visibility(
    client: Client, world_id: str, expected_visible: bool, expected_revision: int
) -> dict[str, Any]:
    snapshot = await wait_for_native_window_revision(client, world_id, expected_revision)
    assert snapshot['window']['visible'] is expected_visible
    return snapshot


def check_discovery_authorization(client: Client) -> None:
    '''验证 discovery 需要 bearer，且不接受带 Origin 的浏览器请求。
    - 🎯使用实际运行时 URL 和令牌，不猜测监听端口
    '''
    endpoint = urlparse(client.descriptor['http_url'])
    assert endpoint.hostname is not None
    port = endpoint.port or 80
    cases = (
        ('missing_bearer', {}),
        (
            'origin_rejected',
            {
                'Authorization': f"Bearer {client.descriptor['token']}",
                'Origin': 'https://example.invalid',
            },
        ),
    )
    for name, headers in cases:
        connection = http.client.HTTPConnection(endpoint.hostname, port, timeout=5)
        try:
            connection.request('GET', '/v1/discovery', headers=headers)
            response = connection.getresponse()
            response.read()
            assert response.status == 401, (name, response.status)
        finally:
            connection.close()


async def raw_call(socket: Any, method: str, params: dict[str, Any]) -> Any:
    '''通过原始 WebSocket 连接执行一个带 request id 的协议调用。
    - 🎯让慢读者不启动 Client 的后台接收任务
    '''
    request_id = uuid.uuid4().hex
    await socket.send(
        json.dumps(
            {'id': request_id, 'method': method, 'params': params},
            ensure_ascii=False,
        )
    )
    while True:
        message = json.loads(await asyncio.wait_for(socket.recv(), timeout=10))
        if message.get('id') != request_id:
            continue
        if message.get('ok'):
            return message.get('result')
        raise RpcError(message.get('error', {}))


async def probe_slow_consumer(
    writer: Client,
    world_id: str,
    join_key: str,
    lease: dict[str, Any],
) -> str:
    '''以真实 WebSocket reader 停止消费快照并要求服务端断开或重同步。
    - 🎯验证有限广播队列的慢消费者故障边界
    '''
    from websockets.asyncio.client import connect

    socket = await connect(
        writer.url,
        additional_headers={
            'Authorization': f"Bearer {writer.descriptor['token']}"
        },
        max_size=1_048_576,
        max_queue=1,
        open_timeout=5,
        ping_interval=None,
    )
    try:
        ready = await raw_call(
            socket,
            'hello',
            {'protocol': '0.3', 'provider_name': 'probe.slow-reader'},
        )
        assert ready['host_id'] == writer.descriptor['host_id']
        await raw_call(
            socket,
            'world.join',
            {'world_id': world_id, 'join_key': join_key, 'mode': 'read'},
        )

        snapshot = await writer.call('world.snapshot', {'world_id': world_id})
        revision = snapshot['revision']
        payload = 'x' * SLOW_PAYLOAD_BYTES
        for counter in range(SLOW_BURST_COUNT):
            try:
                result = await writer.call(
                    'data.replace',
                    {
                        'world_id': world_id,
                        'lease': lease,
                        'expected_revision': revision,
                        'data': {'payload': payload, 'counter': counter},
                    },
                )
            except (ConnectionError, ConnectionClosed) as error:
                raise AssertionError(
                    f'Burst writer disconnected at update {counter}'
                ) from error
            revision = result['revision']
            await asyncio.sleep(SLOW_REQUEST_INTERVAL_SECONDS)

        try:
            async with asyncio.timeout(SLOW_READER_TIMEOUT_SECONDS):
                while True:
                    message = json.loads(await socket.recv())
                    if message.get('event') == 'resync_required':
                        return 'resync_required'
        except ConnectionClosed:
            return 'disconnected'
        except TimeoutError as error:
            raise AssertionError(
                'Slow consumer remained connected without resync after the burst'
            ) from error
    finally:
        await socket.close()


async def run(args: argparse.Namespace) -> None:
    checks: list[str] = []
    async with Client(args.runtime, 'probe.writer-a', args.ws_url) as a:
        created = await a.call(
            'world.create',
            {'window': {'title': '可删除的租约测试世界', 'visible': False}},
        )
        world_id = created['world']['id']
        original_lease = created['lease']
        default_window = created['world']['window']
        assert default_window['surface_opacity'] == 0.8
        assert default_window['title_bar_visible'] is True
        assert default_window['text_selectable'] is True
        assert default_window['click_through'] is False
        checks.append('default_window_appearance_properties')
        await check_legacy_protocol_rejected(a)
        checks.append('previous_protocol_version_is_rejected')
        owner: Client | None = a
        owner_lease = original_lease
        try:
            check_discovery_authorization(a)
            checks.extend(['discovery_requires_bearer', 'origin_is_rejected'])

            async with Client(args.runtime, 'probe.reader-b', args.ws_url) as b:
                await expect_code(
                    b,
                    'world.snapshot',
                    {'world_id': world_id},
                    'FORBIDDEN',
                )
                checks.append('discovery_is_not_read_authorization')
                await expect_code(
                    b,
                    'world.join',
                    {'world_id': world_id, 'mode': 'read'},
                    'FORBIDDEN',
                )
                await b.call(
                    'world.join',
                    {
                        'world_id': world_id,
                        'mode': 'read',
                        'join_key': created['join_key'],
                    },
                )
                checks.append('invite_allows_snapshot_reader')
                await expect_code(
                    b,
                    'world.join',
                    {
                        'world_id': world_id,
                        'mode': 'write',
                        'join_key': created['join_key'],
                    },
                    'WRITE_CONFLICT',
                )
                checks.append('one_writer_only')

                await check_positive_scene_patches(a, world_id, original_lease)
                checks.append('scene_patch_insert_move_replace_props_remove')

                before = await a.call('world.snapshot', {'world_id': world_id})
                await expect_code(
                    a,
                    'scene.patch',
                    {
                        'world_id': world_id,
                        'lease': original_lease,
                        'expected_revision': before['revision'],
                        'ops': [
                            {
                                'op': 'props',
                                'node_id': 'empty',
                                'props': {'text': 'should roll back'},
                            },
                            {'op': 'remove', 'node_id': 'missing'},
                        ],
                    },
                    'NOT_FOUND',
                )
                after = await a.call('world.snapshot', {'world_id': world_id})
                assert before['scene'] == after['scene']
                assert before['revision'] == after['revision']
                checks.append('patch_is_atomic')
                await expect_code(
                    a,
                    'window.configure',
                    {
                        'world_id': world_id,
                        'lease': original_lease,
                        'expected_revision': after['revision'],
                        'patch': {'position': {'x': 10, 'y': 20}},
                    },
                    'HUMAN_GEOMETRY',
                )
                checks.append('human_geometry_not_silently_overwritten')

                visibility = await a.call('world.snapshot', {'world_id': world_id})
                for visible in (True, False, True):
                    await a.mutate(
                        'window.configure',
                        world_id,
                        original_lease,
                        patch={'visible': visible},
                    )
                    visibility = await wait_for_window_visibility(
                        a, world_id, visible, visibility['window_revision'] + 1
                    )
                    assert visibility['epoch'] == original_lease['epoch']
                    assert visibility['writer'] is not None
                checks.append('provider_can_hide_observe_and_restore_without_lease_change')

                opacity = await a.call('world.snapshot', {'world_id': world_id})
                assert abs(opacity['window']['surface_opacity'] - 0.8) < 1e-9
                await a.mutate(
                    'window.configure',
                    world_id,
                    original_lease,
                    patch={'surface_opacity': 0.55},
                )
                opacity = await a.call('world.snapshot', {'world_id': world_id})
                opacity = await wait_for_native_window_revision(
                    a, world_id, opacity['window_revision']
                )
                assert abs(opacity['window']['surface_opacity'] - 0.55) < 1e-9
                assert opacity['epoch'] == original_lease['epoch']
                checks.append('provider_can_read_and_configure_surface_opacity')

                await a.mutate(
                    'window.configure',
                    world_id,
                    original_lease,
                    patch={'title_bar_visible': False, 'click_through': True},
                )
                configured = await a.call('world.snapshot', {'world_id': world_id})
                configured = await wait_for_native_window_revision(
                    a, world_id, configured['window_revision']
                )
                assert configured['window']['title_bar_visible'] is False
                assert configured['window']['click_through'] is True
                assert configured['epoch'] == original_lease['epoch']

                await a.mutate(
                    'window.configure',
                    world_id,
                    original_lease,
                    patch={'title_bar_visible': True, 'click_through': False},
                )
                restored = await a.call('world.snapshot', {'world_id': world_id})
                restored = await wait_for_native_window_revision(
                    a, world_id, restored['window_revision']
                )
                assert restored['window']['title_bar_visible'] is True
                assert restored['window']['click_through'] is False
                assert restored['epoch'] == original_lease['epoch']
                checks.append('provider_can_configure_titlebar_and_clickthrough')

                selectable = await a.call('world.snapshot', {'world_id': world_id})
                assert selectable['window']['text_selectable'] is True
                await a.mutate(
                    'window.configure',
                    world_id,
                    original_lease,
                    patch={'text_selectable': False},
                )
                selectable = await a.call('world.snapshot', {'world_id': world_id})
                assert selectable['window']['text_selectable'] is False
                await a.mutate(
                    'window.configure',
                    world_id,
                    original_lease,
                    patch={'text_selectable': True},
                )
                selectable = await a.call('world.snapshot', {'world_id': world_id})
                assert selectable['window']['text_selectable'] is True
                checks.append('provider_can_read_and_configure_default_text_selection')

                a.heartbeat.cancel()
                await asyncio.gather(a.heartbeat, return_exceptions=True)
                a.heartbeat = None
                lease_ms = a.ready['capabilities']['lease_ms']
                await asyncio.sleep(lease_ms / 1000 + LEASE_EXPIRY_GRACE_SECONDS)
                heartbeat = await a.call('session.ping', {})
                assert world_id not in heartbeat['renewed']
                expired = await b.call(
                    'world.snapshot', {'world_id': world_id}
                )
                assert expired['writer'] is None
                assert expired['status'] == 'stale'
                assert expired['epoch'] > original_lease['epoch']
                checks.append('lease_expires_while_websocket_stays_open')
                await expect_code(
                    a,
                    'lease.renew',
                    {'world_id': world_id, 'lease': original_lease},
                    'STALE_LEASE',
                )
                joined = await b.call(
                    'world.join',
                    {
                        'world_id': world_id,
                        'mode': 'write',
                        'join_key': created['join_key'],
                    },
                )
                assert joined['lease']['epoch'] > original_lease['epoch']
                owner, owner_lease = b, joined['lease']
                await expect_code(
                    a,
                    'data.replace',
                    {
                        'world_id': world_id,
                        'lease': original_lease,
                        'expected_revision': joined['world']['revision'],
                        'data': {'stale': True},
                    },
                    'STALE_LEASE',
                )
                checks.append('expired_writer_is_fenced_after_reacquire')

                disconnected_session = b.ready['session_id']
                disconnected_lease = joined['lease']
                await b.close()
                owner = None

            async with Client(args.runtime, 'probe.reader-b', args.ws_url) as b2:
                assert b2.ready['session_id'] != disconnected_session
                await expect_code(
                    b2,
                    'world.snapshot',
                    {'world_id': world_id},
                    'FORBIDDEN',
                )
                rejoined = await b2.call(
                    'world.join',
                    {
                        'world_id': world_id,
                        'mode': 'write',
                        'join_key': created['join_key'],
                    },
                )
                assert rejoined['lease']['epoch'] > disconnected_lease['epoch']
                owner, owner_lease = b2, rejoined['lease']
                await expect_code(
                    b2,
                    'data.replace',
                    {
                        'world_id': world_id,
                        'lease': disconnected_lease,
                        'expected_revision': rejoined['world']['revision'],
                        'data': {'stale': True},
                    },
                    'STALE_LEASE',
                )
                checks.append('disconnect_clears_membership_and_reconnect_gets_new_epoch')

                slow_result = await probe_slow_consumer(
                    b2, world_id, created['join_key'], owner_lease
                )
                checks.append(f'slow_consumer_{slow_result}')
                await b2.call(
                    'world.destroy',
                    {'world_id': world_id, 'lease': owner_lease},
                )
                owner = None
                checks.append('reconnected_writer_can_destroy_own_world')
        except BaseException:
            print(
                json.dumps(
                    {'status': 'FAIL', 'checks': checks},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            raise
        finally:
            if owner is not None:
                try:
                    await owner.call(
                        'world.destroy',
                        {'world_id': world_id, 'lease': owner_lease},
                    )
                except RpcError as error:
                    if error.code not in ('NOT_FOUND', 'STALE_LEASE', 'SESSION_GONE'):
                        raise
                except (ConnectionError, ConnectionClosed):
                    pass

    print(
        json.dumps(
            {'status': 'PASS', 'host_id': a.ready['host_id'], 'checks': checks},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    args = parser.parse_args()
    require_runtime(parser, args)
    asyncio.run(run(args))
