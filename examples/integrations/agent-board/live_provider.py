'''运行 Codex App、Codex CLI 与 Claude Code 的只读状态纵览
- 🎯复用通用 Agent Board renderer，不让宿主执行 Harness 控制动作
- ⚠️Codex App 连接器快照由有权 Agent 通过 stdin 推送；本地 CLI 不伪装该连接器
'''
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
from pathlib import Path
from typing import Any

PYTHON_EXAMPLES = Path(__file__).resolve().parents[2] / 'python'
if str(PYTHON_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(PYTHON_EXAMPLES))

from client import Client, add_runtime_args, event_world_id, require_runtime  # noqa: E402
from global_overview import (  # noqa: E402
    GlobalOverviewState,
    build_global_overview_scene,
    reconcile_view_state,
    transition_view,
)
from global_overview_provider import cleanup_global_overview_world  # noqa: E402
from live_sources import (  # noqa: E402
    LiveSnapshot,
    SourceReadError,
    load_live_snapshot,
    merge_codex_app_snapshot,
    summarize_live_snapshot,
)

DEFAULT_REFRESH_SECONDS: float = 15.0
'''📜只读来源的默认刷新间隔'''
MIN_REFRESH_SECONDS: float = 5.0
'''📜刷新间隔下限，避免无界启动 CLI 子进程'''
MAX_REFRESH_SECONDS: float = 120.0
'''📜刷新间隔上限'''
DEFAULT_DURATION_SECONDS: int = 600
'''📜Provider 窗口的默认运行时长'''
CODEX_APP_SNAPSHOT_MAX_CHARS: int = 262_144
'''📜Agent-fed Codex App 快照的最大单行字符数'''


def _start_codex_app_snapshot_reader(
    event_loop: asyncio.AbstractEventLoop,
    snapshots: asyncio.Queue[dict[str, Any] | None],
) -> threading.Thread:
    '''将有权 Agent 推送的 JSONL 状态快照送入 asyncio 队列
    - ⚠️不会打印、存盘或执行快照中的文本字段
    - 🚩超大或非法行变为无正文的 disconnected 事件
    '''
    def offer_snapshot(payload: dict[str, Any] | None) -> None:
        if snapshots.full():
            try:
                snapshots.get_nowait()
            except asyncio.QueueEmpty:
                pass
        snapshots.put_nowait(payload)

    def read_lines() -> None:
        try:
            while True:
                line = sys.stdin.readline(CODEX_APP_SNAPSHOT_MAX_CHARS + 1)
                if not line:
                    break
                if not line.strip():
                    continue
                if len(line) > CODEX_APP_SNAPSHOT_MAX_CHARS:
                    while line and not line.endswith('\n'):
                        line = sys.stdin.readline(CODEX_APP_SNAPSHOT_MAX_CHARS + 1)
                    payload = {'source_health': 'disconnected', 'threads': []}
                else:
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        payload = {'source_health': 'disconnected', 'threads': []}
                if isinstance(payload, dict):
                    event_loop.call_soon_threadsafe(offer_snapshot, payload)
                else:
                    event_loop.call_soon_threadsafe(
                        offer_snapshot,
                        {'source_health': 'disconnected', 'threads': []},
                    )
        finally:
            try:
                event_loop.call_soon_threadsafe(offer_snapshot, None)
            except RuntimeError:
                pass

    thread = threading.Thread(target=read_lines, name='codex-app-snapshot-reader', daemon=True)
    thread.start()
    return thread


async def update_view(
    client: Any,
    world_id: str,
    lease: dict[str, Any],
    projection: dict[str, Any],
    state: GlobalOverviewState,
    detail_targets: dict[str, tuple[str, str, str, str]],
    page_count: int,
    event: dict[str, Any],
) -> tuple[GlobalOverviewState, dict[str, tuple[str, str, str, str]], int]:
    '''只处理本地视图导航，不向来源发出任何命令'''
    action = str(event.get('action', ''))
    component_id = str(event.get('component_id', ''))
    next_state = state
    next_targets = dict(detail_targets)
    next_page_count = page_count
    ok = True
    message: str | None = None
    try:
        next_state = transition_view(state, action, component_id, detail_targets, page_count)
        scene, next_targets, next_page_count = build_global_overview_scene(projection, next_state)
        await client.mutate('scene.replace', world_id, dict(lease), scene=scene)
    except Exception as exc:
        ok = False
        message = f'View update failed ({type(exc).__name__}).'
        next_state = state
        next_targets = dict(detail_targets)
        next_page_count = page_count
    await client.call(
        'action.result',
        {
            'world_id': world_id,
            'lease': dict(lease),
            'event_id': event['id'],
            'ok': ok,
            'message': message,
        },
    )
    return next_state, next_targets, next_page_count


async def _refresh_scene(
    client: Any,
    world_id: str,
    lease: dict[str, Any],
    snapshot: LiveSnapshot,
    state: GlobalOverviewState,
) -> tuple[dict[str, tuple[str, str, str, str]], int]:
    '''Render the latest source projection with the shared renderer'''
    scene, detail_targets, page_count = build_global_overview_scene(snapshot.projection, state)
    await client.mutate('scene.replace', world_id, lease, scene=scene)
    return detail_targets, page_count


def _report_snapshot(snapshot: LiveSnapshot) -> None:
    '''Print aggregate source health without session identity or content'''
    report = {'event': 'live-source-snapshot', **summarize_live_snapshot(snapshot)}
    print(json.dumps(report, ensure_ascii=False, separators=(',', ':')), flush=True)


async def run(args: argparse.Namespace) -> None:
    '''Run a read-only overview with local CLI polls and optional Agent-fed Codex App snapshots'''
    world_id: str | None = None
    lease: dict[str, Any] | None = None
    world_deleted = False
    event_task: asyncio.Task[dict[str, Any]] | None = None
    app_snapshot_task: asyncio.Task[dict[str, Any] | None] | None = None
    async with Client(args.runtime, 'python.agent-board.global-overview.live', args.ws_url) as client:
        codex_app_links_enabled = False
        try:
            client.require_capabilities(
                button_features=('external_window_actions', 'codex_thread_navigation')
            )
            codex_app_links_enabled = True
        except RuntimeError:
            # Local metadata remains readable; navigation fails closed without host capability.
            codex_app_links_enabled = False

        created = await client.call(
            'world.create',
            {
                'window': {
                    'title': args.title,
                    'width': 520,
                    'height': 560,
                    'always_on_top': True,
                    'geometry_control': 'human',
                },
                'join_policy': 'invite',
                'claim': True,
            },
        )
        world_id = created['world']['id']
        lease = created.get('lease')
        if not isinstance(lease, dict):
            raise RuntimeError('Host did not issue the live overview writer lease')

        sequence = 1
        snapshot = await asyncio.to_thread(load_live_snapshot, None, sequence=sequence)
        snapshot.projection['codex_app_links_enabled'] = codex_app_links_enabled
        state = GlobalOverviewState()
        try:
            _report_snapshot(snapshot)
            detail_targets, page_count = await _refresh_scene(
                client, world_id, lease, snapshot, state
            )
            print(
                'Live Agent Overview reads Claude Code agents --json, Codex CLI thread/list '
                'with useStateDbOnly=true, and bounded Codex Desktop local metadata. Only '
                'the matched latest agent_message may be read from a local rollout tail; '
                'Codex App connector snapshots are accepted from the authorized Agent stdin bridge.',
                flush=True,
            )

            loop = asyncio.get_running_loop()
            snapshot_queue: asyncio.Queue[dict[str, Any] | None] | None = None
            if args.codex_app_bridge:
                snapshot_queue = asyncio.Queue(maxsize=4)
                _start_codex_app_snapshot_reader(loop, snapshot_queue)
                app_snapshot_task = asyncio.create_task(snapshot_queue.get())
            event_task = asyncio.create_task(client.events.get())
            deadline = loop.time() + args.duration_seconds
            next_refresh = loop.time() + args.refresh_seconds

            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                timeout = min(remaining, max(0.0, next_refresh - loop.time()))
                waiters = [event_task]
                if app_snapshot_task is not None:
                    waiters.append(app_snapshot_task)
                done, _ = await asyncio.wait(
                    waiters,
                    timeout=timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if not done:
                    if loop.time() >= deadline:
                        break
                    sequence += 1
                    snapshot = await asyncio.to_thread(
                        load_live_snapshot,
                        snapshot,
                        sequence=sequence,
                    )
                    snapshot.projection['codex_app_links_enabled'] = codex_app_links_enabled
                    _report_snapshot(snapshot)
                    state = reconcile_view_state(snapshot.projection, state)
                    detail_targets, page_count = await _refresh_scene(
                        client, world_id, lease, snapshot, state
                    )
                    next_refresh = loop.time() + args.refresh_seconds
                    continue

                if event_task in done:
                    message = event_task.result()
                    event_task = asyncio.create_task(client.events.get())
                    event_name = message.get('event')
                    data = message.get('data', {})
                    if event_name == 'world.deleted' and event_world_id(message) == world_id:
                        world_deleted = True
                        return
                    if event_name in ('connection.error', 'connection.closed', 'provider.error'):
                        raise ConnectionError('Live overview connection ended; source data was not written.')
                    if event_name == 'interaction' and isinstance(data, dict) and data.get('world_id') == world_id:
                        state, detail_targets, page_count = await update_view(
                            client,
                            world_id,
                            lease,
                            snapshot.projection,
                            state,
                            detail_targets,
                            page_count,
                            data,
                        )

                if app_snapshot_task is not None and app_snapshot_task in done:
                    payload = app_snapshot_task.result()
                    app_snapshot_task = (
                        asyncio.create_task(snapshot_queue.get()) if payload is not None else None
                    )
                    sequence += 1
                    if payload is None:
                        payload = {'source_health': 'disconnected', 'threads': []}
                    try:
                        snapshot = merge_codex_app_snapshot(
                            snapshot,
                            payload,
                            sequence=sequence,
                            links_enabled=codex_app_links_enabled,
                        )
                    except SourceReadError:
                        snapshot = merge_codex_app_snapshot(
                            snapshot,
                            {'source_health': 'disconnected', 'threads': []},
                            sequence=sequence,
                            links_enabled=codex_app_links_enabled,
                        )
                    _report_snapshot(snapshot)
                    state = reconcile_view_state(snapshot.projection, state)
                    detail_targets, page_count = await _refresh_scene(
                        client, world_id, lease, snapshot, state
                    )
        finally:
            for task in (event_task, app_snapshot_task):
                if task is not None and not task.done():
                    task.cancel()
            if world_id is not None and lease is not None and not world_deleted:
                await cleanup_global_overview_world(client, world_id, lease)


def main() -> None:
    '''Parse local runtime settings and start the read-only provider'''
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument(
        '--duration-seconds',
        type=float,
        default=DEFAULT_DURATION_SECONDS,
        help='How long to keep the live read-only window open (1..3600)',
    )
    parser.add_argument(
        '--refresh-seconds',
        type=float,
        default=DEFAULT_REFRESH_SECONDS,
        help='Refresh interval for local CLI status sources (5..120 seconds)',
    )
    parser.add_argument(
        '--title',
        default='Agent Activity · 全局纵览（本机实时）',
        help='Window title for distinguishing the live status world',
    )
    parser.add_argument(
        '--codex-app-bridge',
        action='store_true',
        help='Accept JSONL snapshots from an authorized Codex App connector Agent over stdin',
    )
    args = parser.parse_args()
    require_runtime(parser, args)
    if not 1 <= args.duration_seconds <= 3600:
        parser.error('--duration-seconds must be between 1 and 3600')
    if not MIN_REFRESH_SECONDS <= args.refresh_seconds <= MAX_REFRESH_SECONDS:
        parser.error('--refresh-seconds must be between 5 and 120')
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
