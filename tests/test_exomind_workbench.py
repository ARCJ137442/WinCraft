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
        '''验证三个活动展示档位都只暴露 WinCraft 本地动作
        - 🤖正常状态不常驻来源健康行，也不把上游身份放入显示数据
        '''
        projection = workbench.project_active_block(active_fixture(), now_ms=10 * 60_000)
        for display_mode in workbench.DISPLAY_MODE_ORDER:
            with self.subTest(display_mode=display_mode):
                data = workbench.build_display_data(projection, display_mode)
                scene = workbench.build_scene(data, display_mode)

                self.assertEqual(self._scene_actions(scene), set(workbench.LOCAL_DISPLAY_ACTIONS))
                self.assertNotIn('taskIds', data)
                self.assertNotIn('actorId', data)
                self.assertNotIn('fixture-profile', json.dumps(data))
                self.assertIn('只读', data['read_only_note'])
                self.assertIsNone(self._find_scene_node(scene, 'source-status'))

    def test_display_mode_cycle_is_local_and_has_three_distinct_levels(self) -> None:
        '''验证 full、compact、mini 的本地循环和节点层级
        - 🤖切换显示模式不创建时间块业务动作
        '''
        self.assertEqual(
            [workbench.next_display_mode(mode) for mode in workbench.DISPLAY_MODE_ORDER],
            ['compact', 'mini', 'full'],
        )

        projection = workbench.project_active_block(active_fixture(), now_ms=10 * 60_000)
        full_scene = workbench.build_scene(
            workbench.build_display_data(projection, 'full'),
            'full',
        )
        compact_scene = workbench.build_scene(
            workbench.build_display_data(projection, 'compact'),
            'compact',
        )
        mini_scene = workbench.build_scene(
            workbench.build_display_data(projection, 'mini'),
            'mini',
        )

        self.assertIsNotNone(self._find_scene_node(full_scene, 'full-heading'))
        self.assertIsNotNone(self._find_scene_node(compact_scene, 'compact-heading'))
        self.assertIsNotNone(self._find_scene_node(compact_scene, 'read-only-note'))
        self.assertIsNotNone(self._find_scene_node(mini_scene, 'mini-hud'))
        mini_data = workbench.build_display_data(projection, 'mini')
        self.assertEqual(mini_data['mini_status'], '进行中 · 只读')
        self.assertIsNone(self._find_scene_node(mini_scene, 'read-only-note'))
        self.assertEqual(self._scene_actions(mini_scene), set(workbench.LOCAL_DISPLAY_ACTIONS))

    def test_idle_surface_has_no_fake_clock_or_start_action(self) -> None:
        '''验证空成功状态使用空闲说明，不伪造时钟或开始控件'''
        projection = workbench.project_read_result(
            workbench.ActiveBlockRead("empty"),
            now_ms=1_000,
        )
        for display_mode in workbench.DISPLAY_MODE_ORDER:
            with self.subTest(display_mode=display_mode):
                data = workbench.build_display_data(projection, display_mode)
                scene = workbench.build_scene(data, display_mode)

                self.assertEqual(data['content_state'], 'idle')
                self.assertEqual(data['title'], '')
                self.assertIsNone(self._find_scene_node(scene, 'title'))
                self.assertIsNone(self._find_scene_node(scene, 'clock'))
                self.assertIsNone(self._find_scene_node(scene, 'mini-clock'))
                self.assertIsNotNone(self._find_scene_node(scene, 'idle-guidance'))
                self.assertEqual(
                    self._scene_actions(scene),
                    set(workbench.LOCAL_DISPLAY_ACTIONS),
                )

    def test_ambiguous_404_remains_a_warning_not_idle(self) -> None:
        '''验证 404 不会被压成真实空闲状态'''
        projection = workbench.project_read_result(
            workbench.ActiveBlockRead("not_found_ambiguous"),
            now_ms=1_000,
        )
        for display_mode in workbench.DISPLAY_MODE_ORDER:
            with self.subTest(display_mode=display_mode):
                data = workbench.build_display_data(projection, display_mode)
                scene = workbench.build_scene(data, display_mode)

                self.assertEqual(data['content_state'], 'projection')
                self.assertEqual(data['source_status'], 'HTTP 404：无活动块或端点需核对')
                self.assertIsNotNone(self._find_scene_node(scene, 'source-status'))
                self.assertIsNone(self._find_scene_node(scene, 'idle-guidance'))

    def test_stale_projection_keeps_last_data_and_shows_source_warning(self) -> None:
        '''验证来源失败时保留最近投影并明确标为陈旧'''
        active = workbench.project_active_block(active_fixture(), now_ms=10 * 60_000)
        stale = workbench.error_projection(active, TimeoutError())
        for display_mode in workbench.DISPLAY_MODE_ORDER:
            with self.subTest(display_mode=display_mode):
                data = workbench.build_display_data(stale, display_mode)
                scene = workbench.build_scene(data, display_mode)

                self.assertEqual(data['content_state'], 'projection')
                self.assertEqual(data['title'], active.title)
                self.assertEqual(data['clock'], active.clock)
                self.assertIn('显示最后一次读取', data['source_status'])
                self.assertIsNotNone(self._find_scene_node(scene, 'source-status'))

    @staticmethod
    def _scene_actions(scene: dict[str, object]) -> set[str]:
        '''读取 fixture 场景中的所有交互动作
        - 🤖递归遍历只服务于组件合同断言
        '''
        actions: set[str] = set()

        def visit(node: dict[str, object]) -> None:
            props = node.get("props")
            if isinstance(props, dict) and isinstance(props.get("action"), str):
                actions.add(props["action"])
            children = node.get("children")
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, dict):
                        visit(child)

        visit(scene['root'])
        return actions

    @staticmethod
    def _find_scene_node(
        scene: dict[str, object],
        node_id: str,
    ) -> dict[str, object] | None:
        '''按稳定节点身份查找 fixture 场景中的组件'''

        def visit(node: dict[str, object]) -> dict[str, object] | None:
            if node.get("id") == node_id:
                return node
            children = node.get("children")
            if isinstance(children, list):
                for child in children:
                    if isinstance(child, dict):
                        result = visit(child)
                        if result is not None:
                            return result
            return None

        root = scene.get('root')
        return visit(root) if isinstance(root, dict) else None

    def test_window_spec_and_size_patches_use_fallbacks_not_measured_sizes(self) -> None:
        '''锁定静态 fallback 请求，不冒充 ExoMind 的 ResizeObserver 稳态尺寸
        - 🤖测试只使用本地合成状态，不创建 WebView 或读取 RT
        '''
        window = workbench.build_window_spec()

        # 🤖ExoMind measures its visible surface after mount; this provider sends these fallbacks.
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
        self.assertEqual(workbench.window_size_patch('full'), {"width": 390, "height": 192})
        self.assertEqual(workbench.window_size_patch('compact'), {"width": 328, "height": 160})
        self.assertEqual(workbench.window_size_patch('mini'), {"width": 248, "height": 120})
        self.assertIn('position_control', workbench.REQUIRED_WINDOW_PROPERTIES)


if __name__ == "__main__":
    unittest.main()
