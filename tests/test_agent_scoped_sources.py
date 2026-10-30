from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_EXAMPLES = ROOT / "examples" / "python"
AGENT_BOARD = ROOT / "examples" / "integrations" / "agent-board"
for import_path in (PROVIDER_EXAMPLES, AGENT_BOARD):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

import scoped_live_sources as scoped  # noqa: E402
from live_sources import LiveSnapshot  # noqa: E402


class ScopedLiveSourceTests(unittest.TestCase):
    def test_composed_scene_has_two_disjoint_source_scope_roots(self):
        value = scoped.scene()
        scene_schema = json.loads(
            (ROOT / "protocol" / "scene.schema.json").read_text(encoding="utf-8")
        )
        theme_schema = json.loads(
            (ROOT / "protocol" / "theme.schema.json").read_text(encoding="utf-8")
        )
        registry = (
            Registry()
            .with_resource(theme_schema["$id"], Resource.from_contents(theme_schema))
            .with_resource(scene_schema["$id"], Resource.from_contents(scene_schema))
        )
        Draft202012Validator(
            scene_schema, format_checker=FormatChecker(), registry=registry
        ).validate(value)

        roots = {child["id"] for child in value["root"]["children"]}
        expected_roots = {
            scoped.LIFECYCLE_SCOPE["root_node_id"],
            *(definition["root_node_id"] for definition in scoped.SOURCE_SCOPES.values()),
        }
        expected_namespaces = {
            scoped.LIFECYCLE_SCOPE["data_namespace"],
            *(definition["data_namespace"] for definition in scoped.SOURCE_SCOPES.values()),
        }
        self.assertTrue(expected_roots.issubset(roots))
        self.assertEqual(set(value["data"]), expected_namespaces)

        def walk(node):
            yield node
            for child in node.get("children", []):
                yield from walk(child)

        for source_id in scoped.SOURCE_IDS:
            panel = next(
                child
                for child in value["root"]["children"]
                if child["id"] == scoped.SOURCE_SCOPES[source_id]["root_node_id"]
            )
            namespace = scoped.SOURCE_SCOPES[source_id]["data_namespace"]
            bindings = [
                prop["$path"]
                for node in walk(panel)
                for prop in node.get("props", {}).values()
                if isinstance(prop, dict) and isinstance(prop.get("$path"), str)
            ]
            self.assertIn(f"/{namespace}/health_label", bindings)
            self.assertTrue(all(path.startswith(f"/{namespace}/") for path in bindings))

        lifecycle_panel = next(
            child
            for child in value["root"]["children"]
            if child["id"] == scoped.LIFECYCLE_SCOPE["root_node_id"]
        )
        lifecycle_bindings = [
            prop["$path"]
            for node in walk(lifecycle_panel)
            for prop in node.get("props", {}).values()
            if isinstance(prop, dict) and isinstance(prop.get("$path"), str)
        ]
        self.assertTrue(lifecycle_bindings)
        self.assertTrue(all(path.startswith("/host/") for path in lifecycle_bindings))

        serialized = json.dumps(value, ensure_ascii=False)
        self.assertNotIn('"action"', serialized)
        self.assertNotIn("native_window_action", serialized)

    def test_scope_projection_keeps_selected_source_and_bounded_safe_fields(self):
        codex_records = [
            {
                "session_id": f"raw-codex-session-{index}",
                "provider_id": "codex-cli",
                "source_status": "active",
                "normalized_status": "running",
                "display_name": f"Codex task {index}",
                "project_label": "Synthetic project",
                "summary": "Synthetic agent output",
            }
            for index in range(5)
        ]
        claude_records = [
            {
                "session_id": "raw-claude-session",
                "provider_id": "claude-code-local-files",
                "source_status": "blocked",
                "normalized_status": "blocked",
                "display_name": "Private Claude task",
                "project_label": "Private project",
                "summary": "Private output",
            }
        ]
        snapshot = LiveSnapshot(
            projection={
                "source_health": {"codex": "online", "claude-code": "offline"},
                "source_data_health": {
                    "codex": "not_applicable",
                    "claude-code": "local_state",
                },
                "source_freshness": {"codex": "fresh", "claude-code": "fresh"},
                "source_age_seconds": {"codex": 2, "claude-code": 9},
            },
            records_by_source={"codex": codex_records, "claude-code": claude_records},
            sequence=1,
            source_observed_at={},
        )

        value = scoped.source_scope_data(snapshot, "codex")
        serialized = json.dumps(value, ensure_ascii=False)

        self.assertEqual(value["record_count"], 5)
        self.assertEqual(len(value["previews"]), scoped.PREVIEW_LIMIT)
        self.assertEqual(value["health_label"], "CLI 可查询")
        self.assertIn("最近成功读取 2 秒前", value["freshness_label"])
        self.assertIn("Codex task 0", serialized)
        self.assertNotIn("Private Claude task", serialized)
        self.assertNotIn("raw-codex-session", serialized)
        self.assertNotIn("raw-claude-session", serialized)
        self.assertNotIn("provider_id", serialized)
        self.assertNotIn("source_status", serialized)

    def test_worker_command_keeps_runtime_and_scope_grant_out_of_arguments(self):
        command = scoped.worker_command("claude-code", 12, None)

        self.assertIn("--source-worker", command)
        self.assertEqual(command[command.index("--source") + 1], "claude-code")
        self.assertNotIn("--runtime", command)
        self.assertNotIn("--join-key", command)
        self.assertNotIn("--scope-id", command)
        with self.assertRaises(ValueError):
            scoped.worker_command("unknown", 12, None)

    def test_worker_bootstrap_is_bound_to_its_source_root(self):
        grant = {
            "scope_id": "00000000-0000-4000-8000-000000000011",
            "root_node_id": "scope-codex",
            "generation": 1,
            "join_key": "synthetic-only-grant",
        }
        payload = json.dumps(
            {"world_id": "00000000-0000-4000-8000-000000000010", "grant": grant}
        ).encode("utf-8")

        world_id, parsed = scoped._validate_worker_payload(payload, "codex")
        self.assertEqual(world_id, "00000000-0000-4000-8000-000000000010")
        self.assertEqual(parsed["root_node_id"], "scope-codex")
        with self.assertRaisesRegex(ValueError, "does not match"):
            scoped._validate_worker_payload(payload, "claude-code")

    def test_lifecycle_projection_displays_only_allowlisted_source_states(self):
        data = scoped._lifecycle_data({"codex": "online", "claude-code": "revoked"})

        self.assertEqual(data["codex_status"], "Writer 在线")
        self.assertEqual(data["codex_tone"], "success")
        self.assertEqual(data["claude_code_status"], "Scope 已撤销")
        self.assertEqual(data["claude_code_tone"], "danger")
        self.assertNotIn("scope_id", json.dumps(data, ensure_ascii=False))
        with self.assertRaisesRegex(ValueError, "both source providers"):
            scoped._lifecycle_data({"codex": "online"})

    def test_scope_status_probe_accepts_only_matching_metadata_without_data(self):
        response = {
            "world_id": "world",
            "scope_id": "scope",
            "requested_generation": 1,
            "current_generation": 1,
            "revision": 4,
            "sequence": 9,
            "status": "stale",
        }
        self.assertEqual(
            scoped._validated_scope_status(
                response,
                world_id="world",
                scope_id="scope",
                generation=1,
            ),
            "stale",
        )
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            scoped._validated_scope_status(
                response,
                world_id="world",
                scope_id="other-scope",
                generation=1,
            )
        with self.assertRaisesRegex(RuntimeError, "business data"):
            scoped._validated_scope_status(
                {**response, "data": {"session_text": "must not be returned"}},
                world_id="world",
                scope_id="scope",
                generation=1,
            )
        with self.assertRaisesRegex(RuntimeError, "unsupported fields"):
            scoped._validated_scope_status(
                {**response, "session_text": "must not be returned"},
                world_id="world",
                scope_id="scope",
                generation=1,
            )
        with self.assertRaisesRegex(RuntimeError, "invalid scope lifecycle metadata"):
            scoped._validated_scope_status(
                {**response, "requested_generation": True},
                world_id="world",
                scope_id="scope",
                generation=1,
            )


if __name__ == "__main__":
    unittest.main()
