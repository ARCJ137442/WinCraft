from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import jsonschema
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
'''Repository root for resolving offline protocol schemas.'''
sys.path.insert(0, str(ROOT / 'examples' / 'python'))
import provider_tutorial  # noqa: E402


def new_state(lesson: int = 0) -> provider_tutorial.TutorialState:
    return {
        'lesson': lesson,
        'message': 'synthetic lesson',
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


def walk(node: dict[str, Any]) -> list[dict[str, Any]]:
    return [node, *(child for item in node.get('children', []) for child in walk(item))]


class FakeMutationClient:
    def __init__(self) -> None:
        self.mutations: list[tuple[str, str, dict[str, Any]]] = []

    async def mutate(
        self,
        method: str,
        world_id: str,
        lease: dict[str, Any],
        **payload: Any,
    ) -> dict[str, Any]:
        self.mutations.append((method, world_id, payload))
        return {'revision': len(self.mutations) + 1}


class FakeDiscoveryClient(FakeMutationClient):
    def __init__(self, worlds: list[dict[str, Any]]) -> None:
        super().__init__()
        self.worlds = worlds
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, method: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append((method, params))
        if method != 'world.list':
            raise AssertionError(f'unexpected tutorial discovery call: {method}')
        return self.worlds


class ProviderTutorialTests(unittest.IsolatedAsyncioTestCase):
    def test_world_request_creates_an_ordinary_invited_world(self) -> None:
        request = provider_tutorial.create_world_request('synthetic tutorial')
        self.assertEqual(request['join_policy'], 'invite')
        self.assertTrue(request['claim'])
        self.assertNotIn('system', request)
        self.assertNotIn('operator', request)

    def test_all_lessons_use_allowlisted_components_and_static_actions(self) -> None:
        self.assertEqual(len(provider_tutorial.LESSONS), 5)
        allowed = {
            'stack', 'row', 'text', 'metric', 'progress', 'badge',
            'button', 'input', 'key_value', 'divider',
        }
        for lesson_index in range(len(provider_tutorial.LESSONS)):
            scene = provider_tutorial.build_scene(new_state(lesson_index))
            nodes = walk(scene['root'])
            self.assertTrue(all(node['kind'] in allowed for node in nodes))
            self.assertTrue(all(isinstance(node['props'].get('action', ''), str) for node in nodes))
            encoded = json.dumps(scene, ensure_ascii=False).lower()
            self.assertNotIn('javascript', encoded)
            self.assertNotIn('<script', encoded)
            self.assertNotIn('"css"', encoded)
            self.assertIn('合成数据', encoded)

    def test_all_lesson_scenes_match_the_offline_protocol_schemas(self) -> None:
        scene_schema = json.loads((ROOT / 'protocol/scene.schema.json').read_text(encoding='utf-8'))
        theme_schema = json.loads((ROOT / 'protocol/theme.schema.json').read_text(encoding='utf-8'))
        registry = Registry().with_resource(
            theme_schema['$id'],
            Resource.from_contents(theme_schema),
        )
        validator = jsonschema.Draft202012Validator(scene_schema, registry=registry)
        for lesson_index in range(len(provider_tutorial.LESSONS)):
            state = new_state(lesson_index)
            state['structure_inserted'] = lesson_index == 1
            state['theme_enabled'] = lesson_index == 3
            state['discovery'] = {
                'worlds': 2,
                'open_authenticated': 1,
                'joined_invite_worlds': 1,
            }
            validator.validate(provider_tutorial.build_scene(state))

    def test_discovery_keeps_only_counts_and_join_policy(self) -> None:
        worlds = [
            {
                'id': 'tutorial',
                'system': False,
                'join_policy': 'invite',
                'title': 'own tutorial',
            },
            {
                'id': 'private-world',
                'system': False,
                'join_policy': 'invite',
                'title': 'PRIVATE NOTE TITLE',
            },
            {
                'id': 'open-world',
                'system': False,
                'join_policy': 'open_authenticated',
                'title': 'PRIVATE DASHBOARD TITLE',
            },
            {
                'id': 'manager',
                'system': True,
                'join_policy': 'invite',
                'title': 'internal manager',
            },
        ]
        summary = provider_tutorial.summarize_discovery(worlds, 'tutorial')
        self.assertEqual(
            summary,
            {'worlds': 2, 'open_authenticated': 1, 'joined_invite_worlds': 1},
        )
        serialized = json.dumps(summary)
        self.assertNotIn('PRIVATE NOTE TITLE', serialized)
        self.assertNotIn('private-world', serialized)

    async def test_dynamic_lesson_inserts_one_component_through_scene_patch(self) -> None:
        state = new_state(lesson=1)
        before = provider_tutorial.build_scene(state)
        area = next(node for node in walk(before['root']) if node['id'] == 'dynamic-area')
        self.assertEqual(area['children'], [])

        client = FakeMutationClient()
        should_finish = await provider_tutorial._handle_action(
            client,
            'tutorial-world',
            {'id': 'lease'},
            state,
            {'action': 'structure.insert'},
        )

        self.assertFalse(should_finish)
        self.assertTrue(state['structure_inserted'])
        patch = client.mutations[0]
        self.assertEqual(patch[0], 'scene.patch')
        operation = patch[2]['ops'][0]
        self.assertEqual(operation['parent'], 'dynamic-area')
        self.assertNotIn('parent_id', operation)
        after = provider_tutorial.build_scene(state)
        self.assertTrue(any(node['id'] == 'inserted-badge' for node in walk(after['root'])))

    async def test_choice_text_theme_and_discovery_actions_use_provider_owned_state(self) -> None:
        state = new_state(lesson=2)
        client = FakeMutationClient()

        for event, expected in (
            ({'action': 'choice.received'}, '提供者确认：已收到。'),
            ({'action': 'message.submit', 'value': 'synthetic note'}, None),
        ):
            should_finish = await provider_tutorial._handle_action(
                client,
                'tutorial-world',
                {'id': 'tutorial-lease'},
                state,
                event,
            )
            self.assertFalse(should_finish)
            self.assertEqual(client.mutations[-1][0], 'data.replace')
            if expected is not None:
                self.assertEqual(state['choice'], expected)
            else:
                self.assertEqual(state['note'], 'synthetic note')

        await provider_tutorial._handle_action(
            client,
            'tutorial-world',
            {'id': 'tutorial-lease'},
            state,
            {'action': 'theme.apply'},
        )
        applied_scene = client.mutations[-1][2]['scene']
        self.assertEqual(client.mutations[-1][0], 'scene.replace')
        self.assertTrue(state['theme_enabled'])
        self.assertIn('theme', applied_scene)

        await provider_tutorial._handle_action(
            client,
            'tutorial-world',
            {'id': 'tutorial-lease'},
            state,
            {'action': 'theme.reset'},
        )
        reset_scene = client.mutations[-1][2]['scene']
        self.assertFalse(state['theme_enabled'])
        self.assertNotIn('theme', reset_scene)

        discovery_client = FakeDiscoveryClient([
            {
                'id': 'tutorial-world',
                'system': False,
                'join_policy': 'invite',
                'title': 'own tutorial',
            },
            {
                'id': 'other-invite-world',
                'system': False,
                'join_policy': 'invite',
                'title': 'PRIVATE USER TITLE',
            },
            {
                'id': 'other-open-world',
                'system': False,
                'join_policy': 'open_authenticated',
                'title': 'PRIVATE DASHBOARD TITLE',
            },
            {
                'id': 'manager-world',
                'system': True,
                'join_policy': 'invite',
                'title': 'internal manager',
            },
        ])
        await provider_tutorial._handle_action(
            discovery_client,
            'tutorial-world',
            {'id': 'tutorial-lease'},
            state,
            {'action': 'discovery.refresh'},
        )

        self.assertEqual(discovery_client.calls, [('world.list', {})])
        self.assertEqual(discovery_client.mutations[-1][0], 'data.replace')
        self.assertEqual(
            state['discovery'],
            {'worlds': 2, 'open_authenticated': 1, 'joined_invite_worlds': 1},
        )
        self.assertNotIn('PRIVATE USER TITLE', json.dumps(state, ensure_ascii=False))
        self.assertNotIn('PRIVATE DASHBOARD TITLE', json.dumps(state, ensure_ascii=False))
        self.assertFalse(any(method in {'world.join', 'world.snapshot'} for method, _ in discovery_client.calls))

    async def test_finish_acknowledges_then_destroys_only_its_own_world_once(self) -> None:
        created_clients: list[Any] = []

        class FakeTutorialClient:
            def __init__(self, runtime: str, name: str, ws_url: str | None) -> None:
                self.events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
                self.calls: list[tuple[str, dict[str, Any]]] = []
                self.order: list[str] = []
                self.events.put_nowait(
                    {
                        'event': 'interaction',
                        'data': {
                            'id': 'event-1',
                            'world_id': 'tutorial-world',
                            'action': 'tutorial.finish',
                        },
                    }
                )
                created_clients.append(self)

            async def __aenter__(self) -> FakeTutorialClient:
                return self

            async def __aexit__(self, *_args: object) -> None:
                return None

            def require_capabilities(self, **kwargs: Any) -> None:
                self.order.append('capabilities')

            async def call(
                self,
                method: str,
                params: dict[str, Any],
            ) -> dict[str, Any]:
                self.calls.append((method, params))
                self.order.append(method)
                if method == 'world.create':
                    return {
                        'world': {'id': 'tutorial-world'},
                        'lease': {'id': 'tutorial-lease', 'epoch': 1},
                    }
                return {}

            async def mutate(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
                return {}

        args = SimpleNamespace(runtime='synthetic-runtime', ws_url=None, title='lesson')
        with patch.object(provider_tutorial, 'Client', FakeTutorialClient):
            await provider_tutorial.run(args)

        client = created_clients[0]
        create_call = next(params for method, params in client.calls if method == 'world.create')
        destroy_calls = [params for method, params in client.calls if method == 'world.destroy']
        result_call = next(params for method, params in client.calls if method == 'action.result')
        self.assertLess(client.order.index('capabilities'), client.order.index('world.create'))
        self.assertNotIn('system', create_call)
        self.assertEqual(len(destroy_calls), 1)
        self.assertEqual(destroy_calls[0]['world_id'], 'tutorial-world')
        self.assertEqual(result_call['world_id'], 'tutorial-world')
        self.assertTrue(result_call['ok'])


if __name__ == '__main__':
    unittest.main()
