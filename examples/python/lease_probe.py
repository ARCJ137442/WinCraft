"""Acceptance probe against the REAL Rust host; no Python model substitutes for it.

- 🤖Covers authorization, lease expiry, disconnect/reconnect fencing, and slow consumers.
"""
from __future__ import annotations

import argparse
import asyncio
import http.client
import json
import uuid
from pathlib import Path
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


async def wait_for_window_event(
    client: Client, subscription_id: str, event_type: str
) -> dict[str, Any]:
    async with asyncio.timeout(5):
        while True:
            message = await client.events.get()
            if message.get('event') != 'window.event':
                continue
            data = message.get('data', {})
            if data.get('subscription_id') == subscription_id and data.get('type') == event_type:
                return data


async def assert_no_window_event(
    client: Client, subscription_id: str, timeout_seconds: float = 0.15
) -> None:
    try:
        async with asyncio.timeout(timeout_seconds):
            while True:
                message = await client.events.get()
                data = message.get('data', {})
                assert not (
                    message.get('event') == 'window.event'
                    and data.get('subscription_id') == subscription_id
                ), 'window state event arrived after the subscription ended'
    except TimeoutError:
        return


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


async def check_optional_form_components(
    client: Client, world_id: str, lease: dict[str, Any]
) -> None:
    """Verify the real Rust host accepts capability-gated popup form structure."""
    client.require_capabilities(
        components=('textarea',),
        keyboard_shortcuts=('escape', 'ctrl_enter'),
        button_features=('selection_groups',),
    )
    scene_path = Path(__file__).resolve().parents[2] / 'protocol' / 'examples' / 'textarea.scene.json'
    scene = json.loads(scene_path.read_text(encoding='utf-8'))
    snapshot = await client.mutate(
        'scene.replace',
        world_id,
        lease,
        scene=scene,
    )
    children = {node['id']: node for node in snapshot['scene']['root']['children']}
    assert children['notes']['kind'] == 'textarea'
    assert children['notes']['props']['value'] == '第一行\n第二行'
    assert children['notes']['props']['shortcut_action'] == 'submit'
    assert children['cancel']['props']['shortcut_action'] == 'cancel.escape'
    assert children['choice-a']['props']['selection_group'] == 'q0'


async def check_theme_tokens(client: Client, world_id: str, lease: dict[str, Any]) -> None:
    '''Verify bounded theme tokens and atomic rejection against the real Rust host.
    - 🎯A rejected theme must not change the scene revision, data, or lease.
    '''
    client.require_capabilities(scene_features=('theme_tokens',))
    fixture_path = Path(__file__).resolve().parents[2] / 'protocol' / 'examples' / 'theme.scene.json'
    theme_scene = json.loads(fixture_path.read_text(encoding='utf-8'))
    accepted = await client.mutate('scene.replace', world_id, lease, scene=theme_scene)
    assert accepted['scene']['theme']['font_scale'] == 1.0
    assert accepted['scene']['theme']['accent'] == '#67E8F9'

    invalid_theme = json.loads(json.dumps(theme_scene))
    invalid_theme['theme']['foreground'] = invalid_theme['theme']['background']
    try:
        await client.mutate('scene.replace', world_id, lease, scene=invalid_theme)
    except RpcError as error:
        assert error.code == 'INVALID_SCENE', error.code
    else:
        raise AssertionError('Low-contrast theme unexpectedly replaced the scene')

    after_rejection = await client.call('world.snapshot', {'world_id': world_id})
    assert after_rejection['revision'] == accepted['revision']
    assert after_rejection['scene'] == accepted['scene']
    still_writable = await client.mutate(
        'data.replace', world_id, lease, data={'theme_probe': 'lease-retained'}
    )
    assert still_writable['scene']['data']['theme_probe'] == 'lease-retained'


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


async def check_scoped_world_discovery(
    owner: Client,
    observer: Client,
    private_world_id: str,
) -> None:
    '''验证 world.list 限于已加入或显式开放世界，且不隐含读取权限。'''
    fixture_title = 'Discovery fixture'
    created_worlds: list[dict[str, Any]] = []
    try:
        for _ in range(2):
            created_worlds.append(await owner.call(
                'world.create',
                {
                    'window': {'title': fixture_title},
                    'join_policy': 'open_authenticated',
                    'claim': False,
                },
            ))

        fixture_ids = {item['world']['id'] for item in created_worlds}
        listed = await observer.call('world.list', {})
        matches = [item for item in listed if item['id'] in fixture_ids]
        assert len(matches) == 2
        assert {item['id'] for item in matches} == fixture_ids
        assert all(item['title'] == fixture_title for item in matches)
        assert all(item['join_policy'] == 'open_authenticated' for item in matches)
        assert all(not any(key in item for key in ('lease', 'join_key', 'scene', 'data')) for item in matches)
        assert all(item['id'] != private_world_id for item in listed)

        for item in matches:
            await expect_code(
                observer,
                'world.snapshot',
                {'world_id': item['id']},
                'FORBIDDEN',
            )
        read_join = await observer.call(
            'world.join',
            {'world_id': matches[0]['id'], 'mode': 'read'},
        )
        assert read_join['world']['id'] == matches[0]['id']
        subscription = await observer.subscribe_events(
            matches[0]['id'], ('window.visibility_changed',),
        )
        write_join = await owner.call(
            'world.join',
            {'world_id': matches[0]['id'], 'mode': 'write'},
        )
        await owner.call(
            'world.destroy',
            {'world_id': matches[0]['id'], 'lease': write_join['lease']},
        )
        async with asyncio.timeout(3):
            while True:
                message = await observer.events.get()
                if message.get('event') == 'world.deleted' and message.get('world_id') == matches[0]['id']:
                    break
        await assert_no_window_event(observer, subscription['subscription_id'])
    finally:
        for item in created_worlds:
            try:
                joined = await owner.call(
                    'world.join',
                    {'world_id': item['world']['id'], 'mode': 'write'},
                )
                await owner.call(
                    'world.destroy',
                    {'world_id': item['world']['id'], 'lease': joined['lease']},
                )
            except RpcError as error:
                if error.code not in ('NOT_FOUND', 'STALE_LEASE', 'SESSION_GONE'):
                    raise


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

        payload = 'x' * SLOW_PAYLOAD_BYTES
        for counter in range(SLOW_BURST_COUNT):
            try:
                result = await writer.mutate(
                    'data.replace', world_id, lease,
                    data={'payload': payload, 'counter': counter},
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
        a.require_capabilities(
            components=('textarea',),
            keyboard_shortcuts=('escape', 'ctrl_enter'),
            button_features=('selection_groups',),
            window_properties=('background_drag_enabled', 'anchor'),
            event_types=('window.geometry_changed', 'window.visibility_changed'),
        )
        checks.append('host_advertises_textarea_escape_and_window_event_capabilities')
        capabilities = a.ready.get('capabilities', {})
        native_windows = capabilities.get('native_windows') is True
        button_features = capabilities.get('button_features', [])
        assert ('external_window_actions' in button_features) == native_windows
        if native_windows:
            a.require_capabilities(button_features=('external_window_actions',))
        checks.append('external_window_action_capability_matches_native_host')
        created = await a.call(
            'world.create',
            {'window': {'title': '可删除的租约测试世界', 'visible': False}},
        )
        world_id = created['world']['id']
        original_lease = created['lease']
        default_window = created['world']['window']
        assert default_window['surface_opacity'] == 0.8
        assert default_window['title_bar_visible'] is True
        assert default_window['background_drag_enabled'] is True
        assert default_window['text_selectable'] is True
        assert default_window['click_through'] is False
        assert default_window['anchor'] is None
        checks.append('default_window_appearance_properties')
        await check_legacy_protocol_rejected(a)
        checks.append('previous_protocol_version_is_rejected')
        owner: Client | None = a
        owner_lease = original_lease
        try:
            check_discovery_authorization(a)
            checks.extend(['discovery_requires_bearer', 'origin_is_rejected'])

            async with Client(args.runtime, 'probe.reader-b', args.ws_url) as b:
                await check_scoped_world_discovery(a, b, world_id)
                checks.extend([
                    'invite_world_metadata_hidden_until_membership',
                    'open_world_list_metadata_does_not_grant_read',
                    'same_display_names_remain_distinct_instances',
                    'world_summary_excludes_credentials_and_scene_data',
                    'world_destroy_event_cleans_state_subscription',
                ])
                await expect_code(
                    b,
                    'world.snapshot',
                    {'world_id': world_id},
                    'FORBIDDEN',
                )
                await expect_code(
                    b,
                    'event.subscribe',
                    {'world_id': world_id, 'types': ['window.visibility_changed']},
                    'FORBIDDEN',
                )
                checks.append('discovery_is_not_read_authorization')
                await expect_code(
                    b,
                    'world.join',
                    {'world_id': world_id, 'mode': 'read'},
                    'FORBIDDEN',
                )
                reader_join = await b.call(
                    'world.join',
                    {
                        'world_id': world_id,
                        'mode': 'read',
                        'join_key': created['join_key'],
                    },
                )
                checks.append('invite_allows_snapshot_reader')
                event_subscription = await b.subscribe_events(
                    world_id,
                    ('window.geometry_changed', 'window.visibility_changed'),
                )
                subscription_id = event_subscription['subscription_id']
                assert event_subscription['sequence'] == reader_join['world']['sequence']
                await expect_code(
                    b,
                    'window.configure',
                    {
                        'world_id': world_id,
                        'lease': original_lease,
                        'expected_revision': reader_join['world']['revision'],
                        'patch': {'visible': False},
                    },
                    'STALE_LEASE',
                )
                checks.append('reader_window_events_are_scoped_and_do_not_grant_write')
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

                await check_optional_form_components(a, world_id, original_lease)
                checks.append('headless_rust_accepts_multiline_popup_scene')

                await check_theme_tokens(a, world_id, original_lease)
                checks.extend([
                    'host_advertises_theme_token_scene_feature',
                    'valid_theme_tokens_accepted',
                    'invalid_theme_rejected_atomically_without_losing_lease',
                ])

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

                await expect_code(
                    a,
                    'window.configure',
                    {
                        'world_id': world_id,
                        'lease': original_lease,
                        'expected_revision': after['revision'],
                        'patch': {
                            'anchor': {
                                'corner': 'bottom_right',
                                'margin_x': 24,
                                'margin_y': 24,
                            },
                        },
                    },
                    'HUMAN_GEOMETRY',
                )
                checks.append('human_geometry_rejects_work_area_anchor')

                anchored = await a.mutate(
                    'window.configure', world_id, original_lease,
                    patch={
                        'geometry_control': 'provider',
                        'anchor': {
                            'corner': 'bottom_right',
                            'margin_x': 24,
                            'margin_y': 24,
                        },
                        'width': 360,
                        'height': 240,
                    },
                )
                assert anchored['window']['anchor'] == {
                    'corner': 'bottom_right', 'margin_x': 24.0, 'margin_y': 24.0,
                }
                checks.append('provider_geometry_anchor_round_trips_through_real_host')
                geometry_event = await wait_for_window_event(
                    b, subscription_id, 'window.geometry_changed'
                )
                assert geometry_event['delivery'] == 'state'
                assert geometry_event['payload']['position'] is None
                assert geometry_event['payload']['anchor'] == {
                    'corner': 'bottom_right', 'margin_x': 24.0, 'margin_y': 24.0,
                }
                assert geometry_event['payload']['width'] == 360
                assert geometry_event['payload']['height'] == 240
                assert geometry_event['source'] == 'provider'
                assert geometry_event['cause_id']
                await assert_no_window_event(b, subscription_id)
                await a.mutate(
                    'window.configure', world_id, original_lease,
                    patch={'geometry_control': 'human'},
                )
                await assert_no_window_event(b, subscription_id)
                checks.append('geometry_state_event_is_typed_latest_and_coalescible')

                visibility = await a.call('world.snapshot', {'world_id': world_id})
                previous_visible = visibility['window']['visible']
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
                    if previous_visible != visible:
                        visibility_event = await wait_for_window_event(
                            b, subscription_id, 'window.visibility_changed'
                        )
                        assert visibility_event['payload']['visible'] is visible
                        assert visibility_event['window_revision'] == visibility['window_revision']
                    previous_visible = visible
                checks.append('provider_can_hide_observe_and_restore_without_lease_change')

                await b.unsubscribe_events(subscription_id)
                await a.mutate(
                    'window.configure', world_id, original_lease,
                    patch={'visible': False},
                )
                await a.mutate(
                    'window.configure', world_id, original_lease,
                    patch={'visible': True},
                )
                await assert_no_window_event(b, subscription_id)
                checks.append('event_unsubscribe_stops_future_state_delivery')

                leave_subscription = await b.subscribe_events(
                    world_id, ('window.visibility_changed',),
                )
                leave_subscription_id = leave_subscription['subscription_id']
                await b.call('world.leave', {'world_id': world_id})
                await b.call(
                    'world.join',
                    {
                        'world_id': world_id,
                        'mode': 'read',
                        'join_key': created['join_key'],
                    },
                )
                await a.mutate(
                    'window.configure', world_id, original_lease,
                    patch={'visible': False},
                )
                await a.mutate(
                    'window.configure', world_id, original_lease,
                    patch={'visible': True},
                )
                await assert_no_window_event(b, leave_subscription_id)
                checks.append('event_subscription_is_removed_on_world_leave')

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

                drag = await a.call('world.snapshot', {'world_id': world_id})
                assert drag['window']['background_drag_enabled'] is True
                drag = await a.mutate(
                    'window.configure',
                    world_id,
                    original_lease,
                    patch={'background_drag_enabled': False},
                )
                assert drag['window']['background_drag_enabled'] is False
                drag = await a.mutate(
                    'window.configure',
                    world_id,
                    original_lease,
                    patch={'background_drag_enabled': True},
                )
                assert drag['window']['background_drag_enabled'] is True
                checks.append('provider_can_read_and_configure_background_drag_handle')

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

                hidden = await b2.mutate(
                    'window.configure',
                    world_id,
                    owner_lease,
                    patch={'visible': False},
                )
                hidden = await wait_for_window_visibility(
                    b2, world_id, False, hidden['window_revision']
                )
                assert hidden['epoch'] == owner_lease['epoch']
                checks.append('slow_consumer_fixture_window_hidden_without_lease_change')

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
