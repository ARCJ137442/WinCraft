'''运行 Codex App、Codex CLI 与 Claude Code 的只读状态纵览
- 🎯复用通用 Agent Board renderer，不让宿主执行 Harness 控制动作
- 📌Codex App 与 Claude Code 的状态来自本机进程观察，详情来自受限磁盘读取
- 🚩不会为采集而启动 Codex App 或 Claude Code
'''
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

PYTHON_EXAMPLES = Path(__file__).resolve().parents[2] / 'python'
if str(PYTHON_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(PYTHON_EXAMPLES))

from client import Client, add_runtime_args, event_world_id, require_runtime  # noqa: E402
from global_overview import (  # noqa: E402
    DetailTarget,
    GlobalOverviewState,
    build_global_overview_scene,
    reconcile_view_state,
    transition_view,
)
from global_overview_provider import cleanup_global_overview_world  # noqa: E402
from live_sources import (  # noqa: E402
    LIVE_SOURCE_LABELS,
    LiveSnapshot,
    load_live_snapshot,
    normalize_live_source_selection,
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


def validate_source_options(
    values: list[str] | tuple[str, ...] | None,
) -> tuple[str, ...]:
    '''验证启动前的来源选择
    - 🤖默认查询全部来源；显式选择可跳过未选择的本机数据源
    '''
    enabled_sources = tuple(values) if values is not None else None
    return normalize_live_source_selection(enabled_sources)


async def update_view(
    client: Any,
    world_id: str,
    lease: dict[str, Any],
    projection: dict[str, Any],
    state: GlobalOverviewState,
    detail_targets: dict[str, DetailTarget],
    page_count: int,
    event: dict[str, Any],
) -> tuple[GlobalOverviewState, dict[str, DetailTarget], int]:
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
) -> tuple[dict[str, DetailTarget], int]:
    '''Render the latest source projection with the shared renderer'''
    scene, detail_targets, page_count = build_global_overview_scene(snapshot.projection, state)
    await client.mutate('scene.replace', world_id, lease, scene=scene)
    return detail_targets, page_count


def _report_snapshot(snapshot: LiveSnapshot) -> None:
    '''Print aggregate source health without session identity or content'''
    report = {'event': 'live-source-snapshot', **summarize_live_snapshot(snapshot)}
    print(json.dumps(report, ensure_ascii=False, separators=(',', ':')), flush=True)


async def run(args: argparse.Namespace) -> None:
    '''Run a read-only overview using local process status and bounded disk snapshots'''
    selected_sources = validate_source_options(args.sources)
    world_id: str | None = None
    lease: dict[str, Any] | None = None
    world_deleted = False
    event_task: asyncio.Task[dict[str, Any]] | None = None
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
        snapshot = await asyncio.to_thread(
            load_live_snapshot,
            None,
            sequence=sequence,
            enabled_sources=selected_sources,
        )
        snapshot.projection['codex_app_links_enabled'] = codex_app_links_enabled
        state = GlobalOverviewState()
        try:
            _report_snapshot(snapshot)
            detail_targets, page_count = await _refresh_scene(
                client, world_id, lease, snapshot, state
            )
            source_labels = ', '.join(LIVE_SOURCE_LABELS[source_id] for source_id in selected_sources)
            print(f'Live Agent Overview selected sources: {source_labels}.', flush=True)
            if 'codex-app' in selected_sources:
                print(
                    'Codex App and Claude Code details are read from bounded local files; process presence '
                    'is reported separately. No Harness process is started for these sources.',
                    flush=True,
                )

            loop = asyncio.get_running_loop()
            event_task = asyncio.create_task(client.events.get())
            deadline = loop.time() + args.duration_seconds
            next_refresh = loop.time() + args.refresh_seconds

            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                timeout = min(remaining, max(0.0, next_refresh - loop.time()))
                done, _ = await asyncio.wait(
                    [event_task],
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
                        enabled_sources=selected_sources,
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

        finally:
            if event_task is not None and not event_task.done():
                event_task.cancel()
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
        help='Refresh interval for local process and session data sources (5..120 seconds)',
    )
    parser.add_argument(
        '--title',
        default='Agent Activity · 全局纵览（本机实时）',
        help='Window title for distinguishing the live status world',
    )
    parser.add_argument(
        '--sources',
        nargs='+',
        choices=tuple(LIVE_SOURCE_LABELS),
        help='Sources to query; default is all. Codex App and Claude Code are read from local files.',
    )
    args = parser.parse_args()
    require_runtime(parser, args)
    try:
        validate_source_options(args.sources)
    except ValueError as error:
        parser.error(str(error))
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
