from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "python"
sys.path.insert(0, str(EXAMPLES))

from obsidian_workspace import build_scene, read_snapshots, write_command  # noqa: E402


class ObsidianWorkspaceProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.plugin = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def snapshot(self, instance_id: str) -> dict[str, object]:
        return {
            "kind": "wincraft.obsidian-workspace.v1",
            "instanceId": instance_id,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "fileCount": 42,
            "latestFileMtime": datetime.now(timezone.utc).isoformat(),
            "workspacePaneCount": 3,
            "activeTitle": "Current page",
            "tabs": ["Current page", "Search"],
            "focus": {"state": "running", "elapsedSeconds": 90, "durationSeconds": 1500},
        }

    def test_given_metadata_snapshot_when_rendered_then_only_workspace_metadata_and_timer_are_projected(self):
        instance_id = "00000000-0000-4000-8000-000000000001"
        snapshot_path = self.plugin / f"{instance_id}.json"
        snapshot_path.write_text(json.dumps(self.snapshot(instance_id)), encoding="utf-8")
        snapshots = read_snapshots(self.plugin)
        scene = build_scene(snapshots, instance_id)
        encoded = json.dumps(scene, ensure_ascii=False)
        self.assertIn("Current page", encoded)
        self.assertIn("Vault 文件数", encoded)
        self.assertIn("25 分钟", encoded)
        self.assertNotIn("markdown", encoded.lower())
        self.assertIn("native_window_action", encoded)
        self.assertIn("已启用插件的窗口", encoded)

    def test_given_focus_button_when_provider_requests_timer_action_then_only_allowlisted_command_is_written(self):
        instance_id = "00000000-0000-4000-8000-000000000001"
        with self.assertRaises(ValueError):
            write_command(self.plugin, instance_id, "focus.execute-anything")
        request_id = write_command(self.plugin, instance_id, "focus.pause")
        command = json.loads((self.plugin / f"{instance_id}.command.json").read_text(encoding="utf-8"))
        self.assertEqual(command["kind"], "wincraft.obsidian-workspace.command.v1")
        self.assertEqual(command["requestId"], request_id)
        self.assertEqual(command["action"], "focus.pause")

    def test_given_multiple_enabled_obsidian_instances_when_rendered_then_user_can_select_one(self):
        first = "00000000-0000-4000-8000-000000000001"
        second = "00000000-0000-4000-8000-000000000002"
        first_snapshot = self.snapshot(first)
        second_snapshot = {**self.snapshot(second), "activeTitle": "Second synthetic tab"}
        (self.plugin / f"{first}.json").write_text(json.dumps(first_snapshot), encoding="utf-8")
        (self.plugin / f"{second}.json").write_text(json.dumps(second_snapshot), encoding="utf-8")
        snapshots = read_snapshots(self.plugin)
        scene = build_scene(snapshots, second)
        encoded = json.dumps(scene, ensure_ascii=False)
        self.assertEqual(len(snapshots), 2)
        self.assertIn("窗口 2 / 2", encoded)
        self.assertIn("Second synthetic tab", encoded)
        self.assertIn("window.select.previous", encoded)
        self.assertIn("window.select.next", encoded)

    def test_given_missing_or_wrong_plugin_snapshot_when_read_then_provider_fails_closed(self):
        self.assertEqual(read_snapshots(self.plugin), [])
        instance_id = "00000000-0000-4000-8000-000000000001"
        path = self.plugin / f"{instance_id}.json"
        path.write_text(json.dumps({"kind": "wrong"}), encoding="utf-8")
        self.assertEqual(read_snapshots(self.plugin), [])


if __name__ == "__main__":
    unittest.main()
