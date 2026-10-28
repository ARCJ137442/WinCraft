"""Parser and projection tests with synthetic fixtures; never live RT evidence."""

from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "python"))

import exomind_workbench as workbench


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]


def active_fixture(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "name": "fixture focus",
        "startId": "fixture-start",
        "startTime": 0,
        "mode": "countdown",
        "targetMinutes": 25,
        "phase": "running",
        "paused": False,
        "transitions": [{"type": "start", "at": 0}],
        "taskIds": ["fixture-task"],
        "actorId": "fixture-actor",
    }
    value.update(overrides)
    return value


class ExoMindWorkbenchProjectionTests(unittest.TestCase):
    def test_running_countdown_is_derived_from_active_block_fields(self) -> None:
        projection = workbench.project_active_block(
            active_fixture(),
            now_ms=10 * 60_000,
        )

        self.assertEqual(projection.status, "进行中")
        self.assertEqual(projection.title, "fixture focus")
        self.assertEqual(projection.clock, "15:00")
        self.assertIn("预计", projection.detail)

    def test_paused_countdown_uses_pause_transition_and_stays_static(self) -> None:
        block = active_fixture(
            phase="paused",
            paused=True,
            pausedAt=10 * 60_000,
            transitions=[
                {"type": "start", "at": 0},
                {"type": "pause", "at": 10 * 60_000},
            ],
        )
        projection = workbench.project_active_block(block, now_ms=30 * 60_000)

        self.assertEqual(projection.status, "已暂停")
        self.assertEqual(projection.clock, "15:00")
        self.assertIn("暂停中", projection.detail)

    def test_404_is_not_proof_that_the_source_is_healthy_or_empty(self) -> None:
        projection = workbench.project_read_result(
            workbench.ActiveBlockRead("not_found_ambiguous"),
            now_ms=1_000,
        )

        self.assertEqual(projection.source_state, "not_found_ambiguous")
        self.assertEqual(projection.status, "状态待核对")
        self.assertIn("端点需要核对", projection.detail)
        self.assertEqual(projection.clock, "--:--")

    def test_empty_success_does_not_create_a_fake_active_block(self) -> None:
        projection = workbench.project_read_result(
            workbench.ActiveBlockRead("empty"),
            now_ms=1_000,
        )

        self.assertEqual(projection.status, "暂无活动时间块")
        self.assertEqual(projection.title, "")
        self.assertEqual(projection.clock, "--:--")

    def test_active_endpoint_is_scoped_and_uses_get_only(self) -> None:
        body = json.dumps(active_fixture()).encode("utf-8")
        with patch.object(workbench, "urlopen", return_value=FakeResponse(body)) as open_url:
            read = workbench.fetch_active_timeblock(
                "http://127.0.0.1:47031",
                "fixture-profile",
                {},
            )

        request = open_url.call_args.args[0]
        self.assertEqual(request.method, "GET")
        self.assertIn("/timeblocks/active?", request.full_url)
        self.assertIn("user_id=fixture-profile", request.full_url)
        self.assertEqual(read.state, "active")

    def test_active_endpoint_404_is_preserved_as_ambiguous(self) -> None:
        not_found = HTTPError(
            "http://127.0.0.1/timeblocks/active",
            404,
            "Not Found",
            {},
            io.BytesIO(b""),
        )
        with patch.object(workbench, "urlopen", side_effect=not_found):
            read = workbench.fetch_active_timeblock(
                "http://127.0.0.1:47031",
                "fixture-profile",
                {},
            )

        self.assertEqual(read.state, "not_found_ambiguous")

    def test_remote_plain_http_and_missing_profile_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            workbench.validate_rt_base("http://example.com")
        with self.assertRaises(ValueError):
            workbench.validate_rt_base("http://127.0.0.1:9124/unexpected")
        with self.assertRaises(ValueError):
            workbench.fetch_active_timeblock(
                "http://127.0.0.1:47031",
                " ",
                {},
            )

    def test_display_scene_has_only_local_actions_and_selected_projection_fields(self) -> None:
        projection = workbench.project_active_block(active_fixture(), now_ms=10 * 60_000)
        data = workbench.build_display_data(projection, compact=False)
        scene = workbench.build_scene(data, compact=False)
        actions: list[str] = []

        def visit(node: dict[str, object]) -> None:
            props = node.get("props")
            if isinstance(props, dict) and isinstance(props.get("action"), str):
                actions.append(props["action"])
            children = node.get("children")
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, dict):
                        visit(child)

        visit(scene["root"])
        self.assertEqual(set(actions), {
            "wincraft.display.toggle",
            "wincraft.display.hide",
        })
        self.assertNotIn("taskIds", data)
        self.assertNotIn("actorId", data)
        self.assertNotIn("fixture-profile", json.dumps(data))
        self.assertIn("只读", data["read_only_note"])

    def test_window_replica_requires_provider_size_but_human_position(self) -> None:
        window = workbench.build_window_spec()

        # These are ExoMind source fallback sizes, not the DOM-measured effective sizes.
        self.assertEqual(window, {
            "title": "外心 · 只读专注工作台",
            "width": 390,
            "height": 192,
            "always_on_top": True,
            "visible": True,
            "resizable": False,
            "title_bar_visible": False,
            "background_drag_enabled": True,
            "text_selectable": False,
            "decorations": False,
            "skip_taskbar": True,
            "surface_opacity": 0.8,
            "geometry_control": "provider",
            "position_control": "human",
        })
        self.assertEqual(workbench.window_size_patch(compact=True), {"width": 248, "height": 120})
        self.assertEqual(workbench.window_size_patch(compact=False), {"width": 390, "height": 192})
        self.assertIn("position_control", workbench.REQUIRED_WINDOW_PROPERTIES)


if __name__ == "__main__":
    unittest.main()
