'''WinCraft 提供者五课新手体验。
- 🎯通过真实 Rust/Tauri host 学习公开协议；课程只使用合成数据。
- 🤖这份教学实现由 Agent 编写，尚待维护者审阅。
'''
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
from pathlib import Path
from typing import Any, TypedDict

from client import Client, RpcError, add_runtime_args, event_world_id, require_runtime
from theme_demo import sample_theme

LESSONS: tuple[tuple[str, str], ...] = (
    (
        '看见第一个世界',
        '这个窗口由 Python 提供者创建。试着拖动它；也可以隐藏后从托盘的世界管理器找回。',
    ),
    (
        '搭一块会变的方块',
        '提供者可以原地更新数据，也可以在连接期间插入、替换或移动声明式组件。',
    ),
    (
        '与程序对话',
        '控件只发出静态动作名和输入值。Python 提供者处理动作、更新状态，再返回回执。',
    ),
    (
        '换一个自己的外观',
        '主题只包含有限 token；标题栏、来源身份、连接状态和本机救援入口仍由宿主管理。',
    ),
    (
        '发现与加入是两件事',
        'world.list 返回元数据；是否能加入仍由目标世界的加入策略与凭证决定。',
    ),
)
'''五课内容的单一来源；顺序变化时，步骤指示和课程导航一起派生。'''

POLL_INTERVAL_SECONDS: float = 1.0
'''恢复隐藏世界时检查 host 快照的间隔。'''


class DiscoverySummary(TypedDict):
    '''只保存世界数量和加入策略计数，不保留世界身份或标题。'''

    worlds: int
    open_authenticated: int
    joined_invite_worlds: int


class TutorialState(TypedDict):
    '''单个教学世界的可重建交互状态。'''

    lesson: int
    message: str
    note: str
    choice: str
    structure_inserted: bool
    theme_enabled: bool
    waiting_for_restore: bool
    discovery: DiscoverySummary


def _node(
    node_id: str,
    kind: str,
    props: dict[str, Any] | None = None,
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    '''建立协议节点；调用点仅使用受支持的固定 component kind。'''
    return {
        'id': node_id,
        'kind': kind,
        'props': props if props is not None else {},
        'children': children if children is not None else [],
    }


def create_world_request(title: str) -> dict[str, Any]:
    '''声明一个普通、受邀请加入的教学世界，不申请宿主 operator 身份。'''
    return {
        'window': {'title': title, 'width': 520, 'height': 560},
        'join_policy': 'invite',
        'claim': True,
    }


def summarize_discovery(
    worlds: list[dict[str, Any]],
    tutorial_world_id: str,
) -> DiscoverySummary:
    '''只汇总外部非系统世界的数量和加入策略，不复制标题、ID或内容。'''
    eligible = [
        world
        for world in worlds
        if world.get('system') is False
        and world.get('id') != tutorial_world_id
    ]
    return {
        'worlds': len(eligible),
        'open_authenticated': sum(
            world.get('join_policy') == 'open_authenticated'
            for world in eligible
        ),
        'joined_invite_worlds': sum(
            world.get('join_policy') == 'invite'
            for world in eligible
        ),
    }


def _scene_data(state: TutorialState) -> dict[str, Any]:
    '''生成供绑定组件读取的本地教学数据。'''
    return {
        'lesson_number': state['lesson'] + 1,
        'lesson_progress': state['lesson'] + 1,
        'message': state['message'],
        'note': state['note'],
        'choice': state['choice'],
        'discovered_worlds': state['discovery']['worlds'],
        'joinable_worlds': state['discovery']['open_authenticated'],
        'joined_invite_worlds': state['discovery']['joined_invite_worlds'],
    }


def build_scene(state: TutorialState) -> dict[str, Any]:
    '''按当前课程搭建普通 WinCraft 组件场景。'''
    lesson_index = state['lesson']
    title, description = LESSONS[lesson_index]
    lesson_children: list[dict[str, Any]] = [
        _node(
            'lesson-heading',
            'text',
            {
                'text': f"第 {lesson_index + 1} 课 · {title}",
                'size': 'heading',
            },
        ),
        _node('lesson-description', 'text', {'text': description}),
        _node(
            'lesson-progress',
            'progress',
            {
                'label': '课程进度',
                'value': {'$path': '/lesson_progress'},
                'max': len(LESSONS),
            },
        ),
        _node(
            'lesson-message',
            'text',
            {'text': {'$path': '/message'}, 'tone': 'muted'},
        ),
    ]

    if lesson_index == 0:
        lesson_children.append(
            _node(
                'hide-world',
                'button',
                {
                    'label': '暂时隐藏，练习从管理器找回',
                    'action': 'world.hide',
                },
            )
        )
    elif lesson_index == 1:
        dynamic_children = (
            [_node('inserted-badge', 'badge', {'text': '这是新插入的组件'})]
            if state['structure_inserted']
            else []
        )
        lesson_children.extend(
            [
                _node(
                    'structure-button',
                    'button',
                    {
                        'label': '插入一个状态徽标',
                        'action': 'structure.insert',
                    },
                ),
                _node(
                    'dynamic-area',
                    'stack',
                    {'gap': 8},
                    dynamic_children,
                ),
            ]
        )
    elif lesson_index == 2:
        lesson_children.extend(
            [
                _node(
                    'choices',
                    'row',
                    {'gap': 8},
                    [
                        _node(
                            'choice-yes',
                            'button',
                            {
                                'label': '收到',
                                'action': 'choice.received',
                            },
                        ),
                        _node(
                            'choice-later',
                            'button',
                            {
                                'label': '稍后处理',
                                'action': 'choice.later',
                            },
                        ),
                    ],
                ),
                _node(
                    'choice-state',
                    'text',
                    {'text': {'$path': '/choice'}, 'tone': 'muted'},
                ),
                _node(
                    'example-input',
                    'input',
                    {
                        'label': '给提供者一条示例消息',
                        'value': {'$path': '/note'},
                        'placeholder': '仅在此教学进程中处理',
                        'action': 'message.submit',
                    },
                ),
            ]
        )
    elif lesson_index == 3:
        lesson_children.extend(
            [
                _node(
                    'theme-actions',
                    'row',
                    {'gap': 8},
                    [
                        _node(
                            'theme-apply',
                            'button',
                            {
                                'label': '应用教学主题',
                                'action': 'theme.apply',
                            },
                        ),
                        _node(
                            'theme-reset',
                            'button',
                            {
                                'label': '恢复宿主默认',
                                'action': 'theme.reset',
                            },
                        ),
                    ],
                ),
                _node(
                    'theme-boundary',
                    'text',
                    {
                        'text': (
                            '请观察：主题只影响内容区，不会伪造来源或授权身份。'
                        ),
                        'tone': 'muted',
                    },
                ),
            ]
        )
    else:
        lesson_children.extend(
            [
                _node(
                    'discovery-count',
                    'metric',
                    {
                        'label': '发现到的其他非系统世界',
                        'value': {'$path': '/discovered_worlds'},
                        'unit': '个',
                        'caption': '只显示计数；没有读取标题或场景',
                    },
                ),
                _node(
                    'join-policies',
                    'key_value',
                    {
                        'items': [
                            {
                                'key': '允许已认证连接申请加入',
                                'value': {'$path': '/joinable_worlds'},
                            },
                            {
                                'key': '已加入的邀请世界',
                                'value': {'$path': '/joined_invite_worlds'},
                            },
                        ]
                    },
                ),
                _node(
                    'discovery-boundary',
                    'text',
                    {
                        'text': (
                            '列表只含已加入或公开开放的世界；未加入邀请世界仍隐藏。'
                            '发现不会取得读写权，本课不打开其他世界；协议 0.3 还没有独立提供者目录。'
                        ),
                        'tone': 'muted',
                    },
                ),
                _node(
                    'discovery-refresh',
                    'button',
                    {
                        'label': '刷新元数据计数',
                        'action': 'discovery.refresh',
                    },
                ),
            ]
        )

    lesson_children.append(
        _node(
            'lesson-navigation',
            'row',
            {'gap': 8},
            [
                _node(
                    'lesson-previous',
                    'button',
                    {
                        'label': '上一课',
                        'action': 'lesson.previous',
                        'disabled': lesson_index == 0,
                    },
                ),
                _node(
                    'lesson-next',
                    'button',
                    {
                        'label': '结束本课' if lesson_index == len(LESSONS) - 1 else '下一课',
                        'action': 'tutorial.finish' if lesson_index == len(LESSONS) - 1 else 'lesson.next',
                        'tone': 'accent',
                    },
                ),
                _node(
                    'tutorial-skip',
                    'button',
                    {'label': '跳过教程', 'action': 'tutorial.finish'},
                ),
            ],
        )
    )

    scene: dict[str, Any] = {
        'root': _node(
            'tutorial-root',
            'stack',
            {'gap': 12},
            [
                _node(
                    'tutorial-banner',
                    'badge',
                    {'text': 'WINCRAFT PROVIDER TUTORIAL · 合成数据'},
                ),
                *lesson_children,
            ],
        ),
        'data': _scene_data(state),
    }
    if state['theme_enabled']:
        scene['theme'] = sample_theme()
    return scene


async def _refresh_discovery(
    client: Client,
    world_id: str,
    state: TutorialState,
) -> None:
    '''读取元数据并丢弃标题、世界 ID 和任何 scene 数据。'''
    worlds = await client.call('world.list', {})
    if not isinstance(worlds, list):
        raise RuntimeError('world.list 返回了无效目录')
    state['discovery'] = summarize_discovery(
        [item for item in worlds if isinstance(item, dict)],
        world_id,
    )


async def _replace_data(
    client: Client,
    world_id: str,
    lease: dict[str, Any],
    state: TutorialState,
) -> None:
    '''只更新本教学世界的数据投影。'''
    await client.mutate(
        'data.replace',
        world_id,
        lease,
        data=_scene_data(state),
    )


async def _publish_lesson(
    client: Client,
    world_id: str,
    lease: dict[str, Any],
    state: TutorialState,
) -> None:
    '''课程切换时整体重建受限声明式场景。'''
    await client.mutate(
        'scene.replace',
        world_id,
        lease,
        scene=build_scene(state),
    )


async def _handle_action(
    client: Client,
    world_id: str,
    lease: dict[str, Any],
    state: TutorialState,
    event: dict[str, Any],
) -> bool:
    '''处理一条教学交互；返回是否应结束并销毁自己的教学世界。'''
    action = event.get('action')
    if action == 'tutorial.finish':
        state['message'] = '正在清理本教程创建的教学世界。'
        return True
    if action in ('lesson.next', 'lesson.previous'):
        offset = 1 if action == 'lesson.next' else -1
        state['lesson'] = min(
            len(LESSONS) - 1,
            max(0, state['lesson'] + offset),
        )
        if state['lesson'] == len(LESSONS) - 1:
            await _refresh_discovery(client, world_id, state)
            state['message'] = '已读取元数据并汇总加入策略；未打开其他世界。'
        else:
            state['message'] = '课程数据由当前 Python 提供者维护。'
        await _publish_lesson(client, world_id, lease, state)
        return False
    if action == 'world.hide':
        await client.mutate(
            'window.configure',
            world_id,
            lease,
            patch={'visible': False},
        )
        state['waiting_for_restore'] = True
        state['message'] = (
            '已提交隐藏请求。请从托盘打开世界管理器并重新显示本窗口；'
            '提供者不能替代本机接管权限。'
        )
        await _replace_data(client, world_id, lease, state)
        return False
    if action == 'structure.insert':
        if state['structure_inserted']:
            state['message'] = '徽标已插入；结构不会因数据刷新而重建。'
        else:
            await client.mutate(
                'scene.patch',
                world_id,
                lease,
                ops=[
                    {
                        'op': 'insert',
                        'parent': 'dynamic-area',
                        'index': 0,
                        'node': _node(
                            'inserted-badge',
                            'badge',
                            {'text': '这是新插入的组件', 'tone': 'success'},
                        ),
                    }
                ],
            )
            state['structure_inserted'] = True
            state['message'] = 'scene.patch 已在连接期间插入组件。'
        await _replace_data(client, world_id, lease, state)
        return False
    if action in ('choice.received', 'choice.later'):
        state['choice'] = (
            '提供者确认：已收到。'
            if action == 'choice.received'
            else '提供者确认：已安排稍后处理。'
        )
        state['message'] = '动作结果来自 Python 提供者，而不是按钮点击本身。'
        await _replace_data(client, world_id, lease, state)
        return False
    if action == 'message.submit':
        value = event.get('value')
        if not isinstance(value, str):
            raise ValueError('消息必须是文本')
        state['note'] = value
        state['message'] = '示例消息只保存在本次教学进程内存中。'
        await _replace_data(client, world_id, lease, state)
        return False
    if action in ('theme.apply', 'theme.reset'):
        state['theme_enabled'] = action == 'theme.apply'
        state['message'] = (
            '已应用有限的 scene.theme tokens。'
            if state['theme_enabled']
            else '已恢复宿主默认主题。'
        )
        await _publish_lesson(client, world_id, lease, state)
        return False
    if action == 'discovery.refresh':
        await _refresh_discovery(client, world_id, state)
        state['message'] = '已刷新加入策略计数，没有加入或读取其他世界。'
        await _replace_data(client, world_id, lease, state)
        return False
    raise ValueError('未知的教学动作')


async def run(args: argparse.Namespace) -> None:
    '''运行教程；清理范围始终限定为本进程创建的唯一教学世界。'''
    world_id: str | None = None
    lease: dict[str, Any] | None = None
    deleted = False
    destroy_attempted = False
    async with Client(args.runtime, 'python.provider-tutorial', args.ws_url) as client:
        client.require_capabilities(scene_features=('theme_tokens',))
        try:
            created = await client.call('world.create', create_world_request(args.title))
        except (TimeoutError, ConnectionError) as error:
            raise RuntimeError(
                'world.create outcome is unknown; inspect the manager before retrying.'
            ) from error
        world = created.get('world')
        world_id = world.get('id') if isinstance(world, dict) else None
        lease = created.get('lease')
        if not isinstance(world_id, str) or not isinstance(lease, dict):
            raise RuntimeError(
                'Host did not return the tutorial world ID and writer lease; '
                'inspect the manager before retrying.'
            )

        state: TutorialState = {
            'lesson': 0,
            'message': '可以跳过任何课程；数据仅为教学示例。',
            'note': '',
            'choice': '尚未处理',
            'structure_inserted': False,
            'theme_enabled': False,
            'waiting_for_restore': False,
            'discovery': {
                'worlds': 0,
                'open_authenticated': 0,
                'joined_invite_worlds': 0,
            },
        }
        print(
            'WinCraft provider tutorial opened with synthetic data. '
            'Ctrl+C disconnects; the script cleans up only its own world.'
        )
        try:
            await _publish_lesson(client, world_id, lease, state)
            while True:
                try:
                    message = await asyncio.wait_for(
                        client.events.get(),
                        timeout=POLL_INTERVAL_SECONDS,
                    )
                except TimeoutError:
                    if state['waiting_for_restore']:
                        snapshot = await client.call(
                            'world.snapshot',
                            {'world_id': world_id},
                        )
                        window = snapshot.get('window', {})
                        native = snapshot.get('native', {})
                        applied = (
                            native.get('state') == 'applied'
                            and native.get('applied_window_revision')
                            == snapshot.get('window_revision')
                        )
                        if window.get('visible') is True and applied:
                            state['waiting_for_restore'] = False
                            state['message'] = (
                                '管理器已恢复原生窗口；继续下一课或跳过。'
                            )
                            await _replace_data(client, world_id, lease, state)
                    continue

                event_name = message.get('event')
                data = message.get('data', {})
                if event_name == 'world.deleted' and event_world_id(message) == world_id:
                    deleted = True
                    return
                if event_name in ('connection.error', 'connection.closed'):
                    raise ConnectionError(
                        'Host connection ended; inspect the manager before starting a new tutorial.'
                    )
                if event_name != 'interaction' or not isinstance(data, dict):
                    continue
                if data.get('world_id') != world_id:
                    continue

                ok = True
                error_message: str | None = None
                should_finish = False
                try:
                    should_finish = await _handle_action(
                        client,
                        world_id,
                        lease,
                        state,
                        data,
                    )
                except (RpcError, ValueError, RuntimeError, ConnectionError) as error:
                    ok = False
                    state['message'] = (
                        f'操作未完成（{type(error).__name__}）；'
                        '请检查宿主状态，不会自动重放写入。'
                    )
                    error_message = f'{type(error).__name__}: tutorial action failed'
                    with contextlib.suppress(RpcError, TimeoutError, ConnectionError):
                        await _replace_data(client, world_id, lease, state)

                await client.call(
                    'action.result',
                    {
                        'world_id': world_id,
                        'lease': lease,
                        'event_id': data['id'],
                        'ok': ok,
                        'message': error_message,
                    },
                )
                if should_finish:
                    destroy_attempted = True
                    try:
                        await client.call(
                            'world.destroy',
                            {'world_id': world_id, 'lease': lease},
                        )
                    except (RpcError, TimeoutError, ConnectionError) as error:
                        raise RuntimeError(
                            'world.destroy outcome is unconfirmed; inspect the manager '
                            'before retrying or closing a world.'
                        ) from error
                    deleted = True
                    print('Tutorial world cleanup confirmed.')
                    return
        finally:
            if world_id and lease and not deleted and not destroy_attempted:
                cleanup = asyncio.create_task(
                    client.call(
                        'world.destroy',
                        {'world_id': world_id, 'lease': lease},
                    )
                )
                try:
                    await asyncio.shield(cleanup)
                    print('Tutorial world cleanup confirmed.')
                except asyncio.CancelledError:
                    with contextlib.suppress(Exception):
                        await asyncio.shield(cleanup)
                        print('Tutorial world cleanup confirmed.')
                    raise
                except Exception:
                    print(
                        'Tutorial cleanup was not confirmed; '
                        'inspect and close only the tutorial world in the manager.',
                        file=sys.stderr,
                    )


def main() -> None:
    '''解析显式运行时参数并启动教学 provider。'''
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument(
        '--title',
        default='WinCraft Agent 新手课程',
        help='用于管理器识别的教学窗口标题',
    )
    args = parser.parse_args()
    require_runtime(parser, args)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
