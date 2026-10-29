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

    def test_provider_source_selection_can_skip_the_stalled_app_bridge(self):
        self.assertEqual(
            validate_source_options(['codex', 'claude-code'], codex_app_bridge=False),
            ('codex', 'claude-code'),
        )
        with self.assertRaises(ValueError):
            validate_source_options(['codex', 'claude-code'], codex_app_bridge=True)

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
