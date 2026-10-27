'''WinCraft scene theme demonstration provider

- 🎯验证受限 theme tokens、host chrome 边界和运行时切换。
- 🤖由 Agent 编写，尚待维护者审阅。
'''
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
from pathlib import Path
from typing import Any

from client import Client, RpcError, add_runtime_args, require_runtime

DEFAULT_TITLE: str = 'Python 提供者 · 主题预览'
'''预览世界的默认标题'''


def sample_theme() -> dict[str, Any]:
    '''读取仓库内的无业务数据主题 fixture。'''
    path = Path(__file__).resolve().parents[2] / 'protocol' / 'examples' / 'theme.scene.json'
    fixture = json.loads(path.read_text(encoding='utf-8'))
    theme = fixture.get('theme')
    if not isinstance(theme, dict):
        raise ValueError('Theme fixture is missing its theme object')
    return theme


def invalid_theme(theme: dict[str, Any]) -> dict[str, Any]:
    '''返回仅用于拒绝测试的低对比 token 副本。'''
    invalid = json.loads(json.dumps(theme))
    invalid['foreground'] = invalid['background']
    return invalid


def _node(
    node_id: str,
    kind: str,
    props: dict[str, Any] | None = None,
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {'id': node_id, 'kind': kind, 'props': props or {}, 'children': children or []}


def build_scene(theme: dict[str, Any] | None, status: str = '') -> dict[str, Any]:
    '''Build a synthetic scene using only standard WinCraft components.'''
    children = [
        _node('theme-banner', 'badge', {'text': 'THEME TOKENS · SYNTHETIC', 'tone': 'accent'}),
        _node('theme-title', 'text', {'text': '沉静主题预览', 'size': 'title'}),
        _node('theme-description', 'text', {
            'text': '主题只改变内容区外观。标题栏、来源身份、连接状态和接管入口仍由 WinCraft 控制。',
        }),
        _node('theme-metrics', 'row', {'gap': 12}, [
            _node('theme-font', 'metric', {'label': '字号', 'value': theme.get('font_scale', '默认') if theme else '默认', 'unit': '×'}),
            _node('theme-radius-metric', 'metric', {'label': '圆角', 'value': theme.get('radius_px', '默认') if theme else '默认', 'unit': 'px'}),
        ]),
        _node('theme-status', 'text', {'text': status or '选择一种主题操作；无效 token 的拒绝不会改变当前 scene。', 'tone': 'muted'}),
        _node('theme-divider', 'divider'),
        _node('theme-actions', 'row', {'gap': 8}, [
            _node('theme-apply', 'button', {'label': '应用示例主题', 'action': 'theme.apply', 'tone': 'accent'}),
            _node('theme-default', 'button', {'label': '恢复宿主默认', 'action': 'theme.default'}),
            _node('theme-invalid', 'button', {'label': '测试无效主题拒绝', 'action': 'theme.invalid', 'tone': 'warning'}),
        ]),
    ]
    scene: dict[str, Any] = {'root': _node('theme-root', 'stack', {'gap': 12}, children), 'data': {}}
    if theme is not None:
        scene['theme'] = theme
    return scene


async def run(args: argparse.Namespace) -> None:
    theme = sample_theme()
    world_id: str | None = None
    lease: dict[str, Any] | None = None
    deleted = False
    async with Client(args.runtime, 'python.theme-demo', args.ws_url) as client:
        client.require_capabilities(scene_features=('theme_tokens',))
        created = await client.call('world.create', {
            'window': {'title': args.title, 'width': 520, 'height': 440},
            'join_policy': 'invite',
            'claim': True,
        })
        world_id, lease = created['world']['id'], created.get('lease')
        if not isinstance(lease, dict):
            raise RuntimeError('Host did not issue a writer lease for the theme preview world')
        print('Theme preview world opened. Its content and actions use synthetic data only.')
        try:
            await client.mutate('scene.replace', world_id, lease, scene=build_scene(theme))
            while True:
                message = await client.events.get()
                name = message.get('event')
                data = message.get('data', {})
                if name == 'world.deleted' and isinstance(data, dict) and data.get('world_id') == world_id:
                    deleted = True
                    return
                if name in ('connection.error', 'connection.closed', 'provider.error'):
                    raise ConnectionError('Theme preview connection ended; the world remains local to the host session.')
                if name != 'interaction' or not isinstance(data, dict) or data.get('world_id') != world_id:
                    continue

                action = data.get('action')
                ok = True
                message_text: str | None = None
                try:
                    if action == 'theme.apply':
                        await client.mutate('scene.replace', world_id, lease, scene=build_scene(theme))
                    elif action == 'theme.default':
                        await client.mutate('scene.replace', world_id, lease, scene=build_scene(None))
                    elif action == 'theme.invalid':
                        before = await client.call('world.snapshot', {'world_id': world_id})
                        try:
                            await client.mutate(
                                'scene.replace',
                                world_id,
                                lease,
                                scene=build_scene(invalid_theme(theme)),
                            )
                        except RpcError as error:
                            if error.code != 'INVALID_SCENE':
                                raise
                            message_text = '主题已拒绝；正在确认原 scene 与租约保持不变。'
                        else:
                            raise RuntimeError('Host accepted the intentionally low-contrast fixture')
                        after = await client.call('world.snapshot', {'world_id': world_id})
                        if after['revision'] != before['revision'] or after['scene'] != before['scene']:
                            raise RuntimeError('Rejected theme changed the current scene')
                        message_text = '主题已拒绝；原 scene、revision 和租约保持不变。'
                    else:
                        raise ValueError('Unknown theme preview action')
                except Exception as error:
                    ok = False
                    message_text = str(error)
                await client.call('action.result', {
                    'world_id': world_id,
                    'lease': lease,
                    'event_id': data['id'],
                    'ok': ok,
                    'message': message_text,
                })
        finally:
            if world_id and lease and not deleted:
                cleanup = asyncio.create_task(client.call(
                    'world.destroy', {'world_id': world_id, 'lease': lease}
                ))
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    with contextlib.suppress(Exception):
                        await asyncio.shield(cleanup)
                    raise
                except Exception:
                    print('Theme preview world cleanup was not confirmed.', file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_runtime_args(parser)
    parser.add_argument('--title', default=DEFAULT_TITLE)
    args = parser.parse_args()
    require_runtime(parser, args)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
