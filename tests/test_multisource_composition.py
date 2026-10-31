import unittest

from examples.python.composition_probe import composition_scene
from examples.python.trafficmonitor_provider import make_view_data as traffic_view_data


def nodes(root):
    yield root
    for child in root.get("children", []):
        yield from nodes(child)


def data_paths(value):
    if isinstance(value, dict):
        if set(value) == {"$path"}:
            yield value["$path"]
            return
        for child in value.values():
            yield from data_paths(child)
    elif isinstance(value, list):
        for child in value:
            yield from data_paths(child)


class CompositionProbeTests(unittest.TestCase):
    def test_real_provider_scenes_are_composed_as_disjoint_read_only_scopes(self):
        traffic = traffic_view_data(None, now_ms=1_800_000_000_000)
        obsidian = {
            "kind": "wincraft.obsidian-workspace.v1",
            "instanceId": "00000000-0000-4000-8000-000000000001",
            "fileCount": 42,
            "workspacePaneCount": 3,
            "activeTitle": "Synthetic page",
            "latestFileMtime": "2026-10-31T00:00:00Z",
            "tabs": ["Synthetic page"],
            "focus": {"state": "idle", "elapsedSeconds": 0, "durationSeconds": 1500},
            "generatedAt": "2026-10-31T00:00:00Z",
            "ageSeconds": 0,
        }
        scene = composition_scene(traffic, obsidian)

        roots = scene["root"]["children"]
        self.assertEqual([root["id"] for root in roots], ["traffic-root", "obsidian-root"])
        self.assertEqual(scene["data"], {"traffic": traffic, "obsidian": obsidian})
        self.assertEqual(
            set(data_paths(scene)),
            {
                "/traffic/status",
                "/traffic/download",
                "/traffic/upload",
                "/traffic/cpu",
                "/traffic/memory",
                "/traffic/gpu",
                "/traffic/app_version",
                "/traffic/sample_time",
            },
        )

        composition_nodes = list(nodes(scene["root"]))
        self.assertTrue(all(node["kind"] not in ("button", "input", "textarea") for node in composition_nodes))
        title = next(node for node in composition_nodes if node["id"] == "obsidian-activate-selected")
        self.assertEqual(title["kind"], "text")
        self.assertNotIn("action", title["props"])
        self.assertNotIn("native_window_action", title["props"])

    def test_traffic_source_failure_projection_keeps_last_reading_for_only_its_scope(self):
        snapshot = {
            "schema": "wincraft.trafficmonitor.v1",
            "sampled_at_ms": 1_800_000_000_000,
            "generation": 7,
            "app_version": "1.8.6.0",
            "download": "12 KB/s",
            "upload": "3 KB/s",
            "cpu": "4%",
            "memory": "37%",
            "gpu": None,
        }
        traffic = traffic_view_data(
            snapshot,
            source_error="桥接文件不存在",
            now_ms=1_800_000_002_000,
        )
        obsidian = {
            "kind": "wincraft.obsidian-workspace.v1",
            "instanceId": "00000000-0000-4000-8000-000000000002",
            "fileCount": 1,
            "workspacePaneCount": 1,
            "activeTitle": "Synthetic page",
            "latestFileMtime": "2026-10-31T00:00:00Z",
            "tabs": ["Synthetic page"],
            "focus": {"state": "idle", "elapsedSeconds": 0, "durationSeconds": 1500},
            "generatedAt": "2026-10-31T00:00:00Z",
            "ageSeconds": 0,
        }
        scene = composition_scene(traffic, obsidian)

        self.assertEqual(traffic["status"], "桥接文件不存在")
        self.assertEqual(traffic["download"], "12 KB/s")
        self.assertEqual(scene["data"]["obsidian"], obsidian)
        self.assertNotEqual(scene["data"]["traffic"], scene["data"]["obsidian"])


if __name__ == "__main__":
    unittest.main()
