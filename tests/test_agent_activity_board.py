import copy
import json
import sys
import unittest
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = ROOT / "examples" / "integrations" / "agent-board"
sys.path.insert(0, str(EXAMPLE_DIR))

from activity_board import (  # noqa: E402
    ACTIVITY_VALIDATOR,
    aggregate_activities,
    build_scene,
    identity_key,
    load_synthetic_activities,
    validate_and_refresh,
)
import provider as agent_board_provider  # noqa: E402


def walk_nodes(node):
    yield node
    for child in node.get("children", []):
        yield from walk_nodes(child)


class AgentActivityBoardTests(unittest.TestCase):
    def setUp(self):
        self.records = load_synthetic_activities()
        self.now = datetime(2026, 10, 29, 10, 2, tzinfo=timezone.utc)

    def test_disconnection_stays_stale_and_never_becomes_idle(self):
        projection = aggregate_activities(self.records, now=self.now)

        self.assertEqual(projection["summary"]["stale_work_items"], 1)
        self.assertEqual(projection["summary"]["active_work_items"], 2)
        stale = next(item for item in projection["sessions"] if item["normalized_status"] == "stale")
        self.assertEqual(stale["freshness"], "disconnected")
        self.assertNotEqual(stale["normalized_status"], "idle")

        invalid = json.loads(
            (EXAMPLE_DIR / "fixtures" / "invalid_disconnected_idle.json").read_text(encoding="utf-8")
        )
        self.assertFalse(ACTIVITY_VALIDATOR.is_valid(invalid))
        with self.assertRaises(ValueError):
            validate_and_refresh([invalid], now=self.now)

    def test_parent_and_child_rollup_counts_only_leaf_sessions(self):
        projection = aggregate_activities(self.records, now=self.now)

        self.assertEqual(projection["summary"]["total_sessions"], 4)
        self.assertEqual(projection["summary"]["counted_work_items"], 3)
        self.assertEqual(projection["summary"]["counting_policy"], "leaf_sessions_only")
        parent = next(item for item in projection["sessions"] if item["identity"][3] == "fixture-parent")
        self.assertFalse(parent["is_leaf"])
        self.assertLess(
            [item["identity"][3] for item in projection["sessions"]].index("fixture-parent"),
            [item["identity"][3] for item in projection["sessions"]].index("fixture-child-running"),
        )

    def test_display_and_model_names_are_not_identity(self):
        first = self.records[0]
        second = self.records[3]
        self.assertEqual(first["display_name"], second["display_name"])
        self.assertEqual(first["model_name"], second["model_name"])
        self.assertNotEqual(identity_key(first), identity_key(second))

        renamed = copy.deepcopy(first)
        renamed["display_name"] = "Renamed display label"
        renamed["model_name"] = "Different model label"
        self.assertEqual(identity_key(first), identity_key(renamed))

        projection = aggregate_activities(self.records, now=self.now)
        rendered_sources = [item["source_type_label"] for item in projection["sessions"]]
        self.assertIn("Codex", rendered_sources)
        self.assertIn("Claude Code", rendered_sources)

    def test_expiry_changes_projection_without_mutating_source_record(self):
        record = copy.deepcopy(self.records[3])
        original = copy.deepcopy(record)
        record["expires_at"] = "2026-10-29T10:01:00Z"

        result = validate_and_refresh([record], now=self.now)

        self.assertEqual(result[0]["freshness"], "stale")
        self.assertEqual(result[0]["normalized_status"], "stale")
        self.assertEqual(record["freshness"], original["freshness"])
        self.assertEqual(record["normalized_status"], original["normalized_status"])

    def test_missing_or_cyclic_parent_fails_closed(self):
        orphan = copy.deepcopy(self.records[1])
        orphan["parent_session_id"] = "missing-parent"
        with self.assertRaisesRegex(ValueError, "parent"):
            validate_and_refresh([orphan], now=self.now)

        first = copy.deepcopy(self.records[0])
        child = copy.deepcopy(self.records[1])
        first["parent_session_id"] = child["session_id"]
        first["source_instance_id"] = child["source_instance_id"]
        child["parent_session_id"] = first["session_id"]
        with self.assertRaisesRegex(ValueError, "cycle"):
            validate_and_refresh([first, child], now=self.now)

    def test_read_only_scene_uses_existing_components_and_hides_source_ids(self):
        projection = aggregate_activities(self.records, now=self.now)
        scene = build_scene(projection)
        schema = json.loads((ROOT / "protocol" / "scene.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(scene)
        nodes = list(walk_nodes(scene["root"]))

        self.assertTrue(nodes)
        self.assertFalse(any(node["kind"] in {"button", "input", "textarea"} for node in nodes))
        for node in nodes:
            props = node.get("props", {})
            self.assertFalse({"action", "context_action", "native_window_action"} & set(props))
        serialized_data = json.dumps(scene["data"], ensure_ascii=False)
        self.assertNotIn("fixture-codex-instance", serialized_data)
        self.assertNotIn("turn.running", serialized_data)
        self.assertNotIn("fixture-task-running", serialized_data)

    def test_control_capabilities_must_remain_empty(self):
        invalid = json.loads(
            (EXAMPLE_DIR / "fixtures" / "invalid_control_capability.json").read_text(encoding="utf-8")
        )
        self.assertFalse(ACTIVITY_VALIDATOR.is_valid(invalid))
        with self.assertRaises(ValueError):
            validate_and_refresh([invalid], now=self.now)


class AgentBoardProviderCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_world_is_destroyed_after_normal_duration(self):
        client = None

        class FakeClient:
            def __init__(self, *_args, **_kwargs):
                nonlocal client
                client = self
                self.destroyed = asyncio.Event()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def call(self, method, _params):
                if method == "world.create":
                    return {"world": {"id": "synthetic-world"}, "lease": {"id": "lease-a"}}
                if method == "world.destroy":
                    self.destroyed.set()
                    return {"world_id": "synthetic-world"}
                raise AssertionError(f"unexpected RPC method: {method}")

            async def mutate(self, *_args, **_kwargs):
                return {"revision": 2}

        args = SimpleNamespace(
            runtime="synthetic-descriptor", ws_url=None, title="Synthetic Agent Board", duration_seconds=0
        )
        with patch.object(agent_board_provider, "Client", FakeClient):
            await agent_board_provider.run(args)
        self.assertTrue(client.destroyed.is_set())

    async def test_world_is_destroyed_before_provider_cancellation_propagates(self):
        client = None
        client_created = asyncio.Event()

        class FakeClient:
            def __init__(self, *_args, **_kwargs):
                nonlocal client
                client = self
                self.published = asyncio.Event()
                self.destroyed = asyncio.Event()
                client_created.set()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def call(self, method, _params):
                if method == "world.create":
                    return {"world": {"id": "synthetic-world"}, "lease": {"id": "lease-a"}}
                if method == "world.destroy":
                    self.destroyed.set()
                    return {"world_id": "synthetic-world"}
                raise AssertionError(f"unexpected RPC method: {method}")

            async def mutate(self, *_args, **_kwargs):
                self.published.set()
                return {"revision": 2}

        args = SimpleNamespace(
            runtime="synthetic-descriptor", ws_url=None, title="Synthetic Agent Board", duration_seconds=60
        )
        with patch.object(agent_board_provider, "Client", FakeClient):
            task = asyncio.create_task(agent_board_provider.run(args))
            await asyncio.wait_for(client_created.wait(), timeout=1)
            await asyncio.wait_for(client.published.wait(), timeout=1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(client.destroyed.is_set())


if __name__ == "__main__":
    unittest.main()
