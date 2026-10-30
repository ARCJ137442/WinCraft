import asyncio
import copy
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = ROOT / "examples" / "integrations" / "agent-board"
sys.path.insert(0, str(EXAMPLE_DIR))

from global_overview import (  # noqa: E402
    MAX_CLAUDE_PREVIEW_SESSIONS,
    GlobalOverviewState,
    build_global_overview_scene,
    load_synthetic_global_projection,
    transition_view,
)
from global_overview_provider import (  # noqa: E402
    cleanup_global_overview_world,
    handle_view_interaction,
)
from live_provider import validate_source_options  # noqa: E402
import global_overview_provider as overview_provider  # noqa: E402


def walk_nodes(node):
    yield node
    for child in node.get("children", []):
        yield from walk_nodes(child)


class GlobalOverviewSceneTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 29, 10, 2, tzinfo=timezone.utc)
        self.projection = load_synthetic_global_projection(now=self.now)

    def test_provider_source_selection_uses_only_known_local_sources(self):
        self.assertEqual(
            validate_source_options(['codex', 'claude-code']),
            ('codex', 'claude-code'),
        )
        with self.assertRaises(ValueError):
            validate_source_options(['codex', 'unknown'])

    def test_default_scene_shows_global_counts_and_bounded_claude_status_preview(self):
        scene, detail_targets, page_count = build_global_overview_scene(
            self.projection, GlobalOverviewState()
        )

        schema = json.loads((ROOT / "protocol" / "scene.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(scene)
        self.assertEqual(page_count, 1)
        self.assertGreaterEqual(scene["data"]["summary"]["codex_parallel"], 0)
        self.assertGreater(scene["data"]["summary"]["claude_sessions"], 0)
        self.assertLessEqual(
            len(scene["data"]["claude_preview"]), MAX_CLAUDE_PREVIEW_SESSIONS
        )
        self.assertTrue(detail_targets)
        self.assertTrue(all(item["status"] and item["freshness"] for item in scene["data"]["claude_preview"]))
        self.assertTrue(all(item["project"] and item["output"] for item in scene["data"]["claude_preview"]))
        self.assertTrue(scene["data"]["codex_cli_preview"])
        self.assertTrue(
            all(
                item["name"] and item["status"] and item["project"] and item["output"]
                for item in scene["data"]["codex_cli_preview"]
            )
        )

        nodes = list(walk_nodes(scene["root"]))
        claude_preview_row = next(
            node for node in nodes if node["id"].startswith("global-claude-preview-row-")
        )
        self.assertEqual(claude_preview_row["kind"], "stack")
        self.assertTrue(
            any(node["id"].startswith("global-claude-preview-project-") for node in nodes)
        )
        self.assertTrue(
            any(node["id"].startswith("global-claude-preview-output-") for node in nodes)
        )
        self.assertTrue(
            any(node["id"].startswith("global-codex-cli-preview-name-") for node in nodes)
        )
        self.assertTrue(
            any(node["id"].startswith("global-codex-cli-preview-status-") for node in nodes)
        )
        self.assertTrue(
            any(node["id"].startswith("global-codex-cli-preview-project-") for node in nodes)
        )
        self.assertTrue(
            any(node["id"].startswith("global-codex-cli-preview-output-") for node in nodes)
        )
        actions = [node["props"]["action"] for node in nodes if node["kind"] == "button"]
        self.assertTrue(actions)
        self.assertTrue(all(action.startswith("view.") for action in actions))
        self.assertFalse(any(node["kind"] in {"input", "textarea"} for node in nodes))
        for node in nodes:
            self.assertNotIn("native_window_action", node.get("props", {}))
            self.assertNotIn("context_action", node.get("props", {}))

        serialized = json.dumps(scene, ensure_ascii=False)
        self.assertNotIn("fixture-codex-instance", serialized)
        self.assertNotIn("turn.running", serialized)
        self.assertNotIn("source_status", serialized)

    def test_not_requested_app_source_is_not_rendered_as_empty_or_offline(self):
        projection = copy.deepcopy(self.projection)
        projection['source_health']['codex-app'] = 'not_requested'
        projection['source_age_seconds'] = {'codex-app': None}
        projection['source_freshness'] = {'codex-app': 'unknown'}
        projection['data_mode_label'] = '本机 CLI 实时只读 · Codex App 本轮未查询'

        scene, _, _ = build_global_overview_scene(projection, GlobalOverviewState())

        self.assertEqual(scene['data']['summary']['codex_app_health'], '本轮未查询')
        self.assertEqual(scene['data']['summary']['codex_app_updated'], '本轮未查询')
        self.assertEqual(scene['data']['summary']['codex_app_sessions'], 0)

    def test_live_scene_separates_health_data_quality_and_freshness_for_all_sources(self):
        projection = copy.deepcopy(self.projection)
        projection['data_mode_label'] = '本机进程与文件实时只读'
        projection['source_health'] = {
            'codex': 'online',
            'codex-app': 'online',
            'claude-code': 'offline',
        }
        projection['source_data_health'] = {
            'codex-app': 'partial',
            'claude-code': 'partial',
        }
        projection['source_age_seconds'] = {
            'codex': 0,
            'codex-app': 4,
            'claude-code': 12,
        }
        projection['source_freshness'] = {
            'codex': 'fresh',
            'codex-app': 'fresh',
            'claude-code': 'fresh',
        }

        scene, _, _ = build_global_overview_scene(
            projection,
            GlobalOverviewState(),
        )

        schema = json.loads((ROOT / 'protocol' / 'scene.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(scene)
        nodes = {node['id']: node for node in walk_nodes(scene['root'])}
        source_fields = {
            'codex': ('codex_cli_health', 'codex_cli_updated'),
            'codex-app': ('codex_app_health', 'codex_app_updated'),
            'claude-code': ('claude_health', 'claude_updated'),
        }
        for source_id, (health_key, freshness_key) in source_fields.items():
            self.assertIn(f'global-{source_id}-health', nodes)
            freshness = nodes[f'global-{source_id}-freshness']
            self.assertEqual(
                freshness['props']['text'],
                {'$path': f'/summary/{freshness_key}'},
            )
            self.assertTrue(scene['data']['summary'][freshness_key])

        self.assertEqual(scene['data']['summary']['codex_health'], '进程在线')
        self.assertEqual(scene['data']['summary']['codex_cli_health'], 'CLI 可查询')
        self.assertEqual(scene['data']['summary']['codex_app_health'], '进程在线')
        self.assertEqual(scene['data']['summary']['claude_health'], '进程离线')
        self.assertNotIn('桥接', scene['data']['summary']['codex_app_health'])
        self.assertIn('0 秒前', scene['data']['summary']['codex_cli_updated'])
        self.assertIn('4 秒前', scene['data']['summary']['codex_app_updated'])
        self.assertIn('12 秒前', scene['data']['summary']['claude_updated'])
        self.assertIn('global-codex-app-data-health', nodes)
        self.assertIn('global-claude-code-data-health', nodes)

        offline_projection = copy.deepcopy(projection)
        offline_projection['source_health']['codex-app'] = 'offline'
        offline_scene, _, _ = build_global_overview_scene(
            offline_projection,
            GlobalOverviewState(),
        )
        self.assertEqual(
            offline_scene['data']['summary']['codex_app_health'],
            '进程离线',
        )

        unavailable_projection = copy.deepcopy(projection)
        unavailable_projection['source_health']['codex-app'] = 'unavailable'
        unavailable_scene, _, _ = build_global_overview_scene(
            unavailable_projection,
            GlobalOverviewState(),
        )
        self.assertEqual(
            unavailable_scene['data']['summary']['codex_app_health'],
            '进程状态不可用',
        )

    def test_codex_app_preview_binds_name_status_project_output_and_uuid_link(self):
        projection = copy.deepcopy(self.projection)
        projection['data_mode_label'] = '本机进程与文件实时只读'
        projection['source_health'] = {
            'codex': 'online',
            'codex-app': 'online',
            'claude-code': 'offline',
        }
        projection['source_data_health'] = {
            'codex-app': 'local_state',
            'claude-code': 'partial',
        }
        projection['source_age_seconds'] = {
            'codex': 0,
            'codex-app': 2,
            'claude-code': 12,
        }
        projection['source_freshness'] = {
            'codex': 'fresh',
            'codex-app': 'fresh',
            'claude-code': 'fresh',
        }
        projection['codex_app_links_enabled'] = True
        session = copy.deepcopy(projection['sessions'][0])
        identity = tuple(session['identity'])
        session.update(
            {
                'identity': (*identity[:3], 'synthetic-codex-app-thread'),
                'source_type_label': 'Codex App',
                'display_name': 'Synthetic Codex App title',
                'normalized_status': 'running',
                'status_label': '运行中',
                'freshness': 'fresh',
                'freshness_label': '刚刚读取（2 秒前）',
                'project_label': 'SyntheticProject',
                'summary': 'Synthetic latest agent output',
                'last_output_kind': 'agent_message',
                'codex_app_thread_id': '00000000-0000-4000-8000-000000000042',
                'is_leaf': True,
            }
        )
        projection['sessions'].append(session)

        scene, _, _ = build_global_overview_scene(
            projection,
            GlobalOverviewState(),
        )

        schema = json.loads((ROOT / 'protocol' / 'scene.schema.json').read_text(encoding='utf-8'))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(scene)
        self.assertEqual(len(scene['data']['codex_app_preview']), 1)
        preview = scene['data']['codex_app_preview'][0]
        self.assertEqual(preview['status'], '运行中')
        self.assertEqual(preview['freshness'], '刚刚读取（2 秒前）')
        self.assertEqual(preview['project'], '项目：SyntheticProject')
        self.assertEqual(preview['output'], '最近 Agent 输出：Synthetic latest agent output')

        nodes = list(walk_nodes(scene['root']))
        title = next(
            node
            for node in nodes
            if node['id'].startswith('global-codex-app-preview-name-')
        )
        self.assertEqual(title['kind'], 'button')
        self.assertEqual(title['props']['label'], 'Synthetic Codex App title')
        self.assertEqual(title['props']['action'], 'view.open_detail')
        self.assertEqual(
            title['props']['native_window_action'],
            {
                'application': 'codex_app',
                'operation': 'open_thread',
                'thread_id': '00000000-0000-4000-8000-000000000042',
            },
        )

    def test_source_switch_and_detail_are_progressive_and_return_to_same_source(self):
        source_state = transition_view(
            GlobalOverviewState(), "view.source.claude_code", "", {}, 1
        )
        self.assertEqual(source_state.source, "claude-code")
        scene, detail_targets, page_count = build_global_overview_scene(
            self.projection, source_state
        )
        expected_sessions = sum(
            session["source_type_label"] == "Claude Code"
            for session in self.projection["sessions"]
        )
        self.assertEqual(len(scene["data"]["sessions"]), expected_sessions)
        self.assertTrue(detail_targets)

        button_id = next(iter(detail_targets))
        detail_state = transition_view(
            source_state, "view.open_detail", button_id, detail_targets, page_count
        )
        detail_scene, _, _ = build_global_overview_scene(self.projection, detail_state)
        schema = json.loads((ROOT / "protocol" / "scene.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(detail_scene)
        detail = detail_scene["data"]["detail"]
        self.assertEqual(detail["source"], "Claude Code")
        self.assertTrue(detail["status"])
        self.assertTrue(detail["freshness"])
        self.assertNotIn("source_status", detail)
        self.assertNotIn("sequence", detail)
        self.assertNotIn("turn.running", json.dumps(detail, ensure_ascii=False))

        back_state = transition_view(detail_state, "view.back", "", {}, page_count)
        self.assertEqual((back_state.source, back_state.selected_identity), ("claude-code", None))
        all_state = transition_view(back_state, "view.all", "", {}, page_count)
        self.assertEqual((all_state.source, all_state.page), ("all", 0))

    def test_detail_action_must_belong_to_the_current_render(self):
        with self.assertRaisesRegex(ValueError, "current rendered view"):
            transition_view(
                GlobalOverviewState(source="claude-code"),
                "view.open_detail",
                "stale-component-from-previous-revision",
                {},
                1,
            )

    def test_empty_source_has_an_explicit_empty_state(self):
        projection = copy.deepcopy(self.projection)
        projection["sessions"] = [
            session
            for session in projection["sessions"]
            if session["source_type_label"] == "Codex"
        ]
        scene, _, _ = build_global_overview_scene(
            projection, GlobalOverviewState(source="claude-code")
        )
        self.assertEqual(scene["data"]["sessions"], [])
        text_values = [
            node["props"].get("text")
            for node in walk_nodes(scene["root"])
            if node["kind"] == "text"
        ]
        self.assertIn("该来源当前没有可显示的会话。", text_values)

    def test_source_list_pagination_is_bounded_and_reversible(self):
        projection = copy.deepcopy(self.projection)
        claude = [
            session
            for session in projection["sessions"]
            if session["source_type_label"] == "Claude Code"
        ]
        template = next(session for session in claude if session["is_leaf"])
        for index in range(7):
            extra = copy.deepcopy(template)
            identity = list(extra["identity"])
            identity[3] = f"fixture-extra-{index}"
            extra["identity"] = identity
            extra["display_name"] = f"Synthetic Claude session {index}"
            projection["sessions"].append(extra)

        state = GlobalOverviewState(source="claude-code")
        first_scene, _, page_count = build_global_overview_scene(
            projection, state, page_size=2
        )
        self.assertGreater(page_count, 1)
        self.assertEqual(len(first_scene["data"]["sessions"]), 2)

        next_state = transition_view(state, "view.page.next", "", {}, page_count)
        second_scene, _, _ = build_global_overview_scene(projection, next_state, page_size=2)
        self.assertEqual(next_state.page, 1)
        self.assertEqual(len(second_scene["data"]["sessions"]), 2)
        self.assertNotEqual(
            first_scene["data"]["sessions"][0]["name"],
            second_scene["data"]["sessions"][0]["name"],
        )
        previous_state = transition_view(next_state, "view.page.previous", "", {}, page_count)
        self.assertEqual(previous_state.page, 0)


class GlobalOverviewProviderActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_navigation_replaces_scene_and_acknowledges_without_business_action(self):
        projection = load_synthetic_global_projection(
            now=datetime(2026, 10, 29, 10, 2, tzinfo=timezone.utc)
        )
        state = GlobalOverviewState()
        _, detail_targets, page_count = build_global_overview_scene(projection, state)
        client = SimpleNamespace(scenes=[], acknowledgements=[])

        async def mutate(_method, _world_id, _lease, **kwargs):
            client.scenes.append(kwargs["scene"])
            return {"revision": len(client.scenes) + 1}

        async def call(method, payload):
            self.assertEqual(method, "action.result")
            client.acknowledgements.append(payload)
            return {"ok": True}

        client.mutate = mutate
        client.call = call
        event = {
            "id": "synthetic-action-1",
            "component_id": "view-tab-claude",
            "action": "view.source.claude_code",
        }

        next_state, next_targets, next_page_count = await handle_view_interaction(
            client,
            "synthetic-world",
            {"id": "synthetic-lease", "epoch": 1},
            projection,
            state,
            detail_targets,
            page_count,
            event,
        )

        self.assertEqual(next_state.source, "claude-code")
        self.assertEqual(next_page_count, 1)
        self.assertTrue(next_targets)
        self.assertEqual(len(client.scenes), 1)
        self.assertEqual(client.acknowledgements[0]["event_id"], "synthetic-action-1")
        self.assertTrue(client.acknowledgements[0]["ok"])
        actions = [
            node["props"]["action"]
            for node in walk_nodes(client.scenes[0]["root"])
            if node["kind"] == "button"
        ]
        self.assertTrue(all(action.startswith("view.") for action in actions))

    async def test_stale_view_action_fails_and_keeps_current_scene_state(self):
        projection = load_synthetic_global_projection(
            now=datetime(2026, 10, 29, 10, 2, tzinfo=timezone.utc)
        )
        state = GlobalOverviewState(source="claude-code")
        _, detail_targets, page_count = build_global_overview_scene(projection, state)
        client = SimpleNamespace(scenes=[], acknowledgements=[])

        async def mutate(*_args, **_kwargs):
            client.scenes.append("mutated")

        async def call(_method, payload):
            client.acknowledgements.append(payload)

        client.mutate = mutate
        client.call = call
        event = {
            "id": "synthetic-stale-action",
            "component_id": "old-detail-button",
            "action": "view.open_detail",
        }

        next_state, next_targets, next_page_count = await handle_view_interaction(
            client,
            "synthetic-world",
            {"id": "synthetic-lease", "epoch": 1},
            projection,
            state,
            detail_targets,
            page_count,
            event,
        )

        self.assertEqual(next_state, state)
        self.assertEqual(next_targets, detail_targets)
        self.assertEqual(next_page_count, page_count)
        self.assertEqual(client.scenes, [])
        self.assertFalse(client.acknowledgements[0]["ok"])
        self.assertEqual(client.acknowledgements[0]["message"], "View update failed (ValueError).")

    async def test_local_manager_close_is_confirmed_by_read_only_snapshot(self):
        class NotFound(Exception):
            code = "NOT_FOUND"

        class FakeClient:
            def __init__(self):
                self.methods = []

            async def call(self, method, _params):
                self.methods.append(method)
                raise NotFound("synthetic world already removed")

        client = FakeClient()
        await cleanup_global_overview_world(
            client,
            "synthetic-world",
            {"id": "synthetic-lease", "epoch": 1},
        )
        self.assertEqual(client.methods, ["world.destroy", "world.snapshot"])

    async def test_top_level_world_deleted_stops_provider_without_destroy_retry(self):
        calls = []

        class FakeClient:
            def __init__(self, *_args, **_kwargs):
                self.events = asyncio.Queue()
                self.events.put_nowait({"event": "world.deleted", "world_id": "synthetic-world"})

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def call(self, method, _params):
                calls.append(method)
                if method == "world.create":
                    return {
                        "world": {"id": "synthetic-world"},
                        "lease": {"id": "synthetic-lease", "epoch": 1},
                    }
                raise AssertionError(f"unexpected RPC method after world deletion: {method}")

            async def mutate(self, method, _world_id, _lease, **_kwargs):
                calls.append(method)
                return {"revision": 2}

        args = SimpleNamespace(
            runtime="synthetic-descriptor",
            ws_url=None,
            title="Synthetic overview",
            duration_seconds=60,
        )
        with patch.object(overview_provider, "Client", FakeClient):
            await overview_provider.run(args)
        self.assertEqual(calls, ["world.create", "scene.replace"])


if __name__ == "__main__":
    unittest.main()
