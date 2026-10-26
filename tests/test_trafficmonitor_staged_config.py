from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from examples.trafficmonitor.configure_staged_copy import (
    BRIDGE_DLL,
    STAGE_MARKER,
    STAGE_MARKER_CONTENT,
    configure_staged_copy,
    enable_bridge_item,
)


class StagedTrafficMonitorConfigTests(unittest.TestCase):
    def test_empty_item_is_enabled_without_rewriting_other_bytes(self) -> None:
        original = (
            b"[General]\r\n"
            b"name=fixture\r\n"
            b"plugin_display_item=\r\n"
            b"other=\xff\r\n"
        )
        updated, changed = enable_bridge_item(original)
        self.assertTrue(changed)
        self.assertEqual(
            updated,
            original.replace(b"plugin_display_item=\r\n", b"plugin_display_item=wincraft.bridge\r\n"),
        )

    def test_existing_bridge_item_is_idempotent(self) -> None:
        original = b"plugin_display_item=wincraft.bridge\r\n"
        updated, changed = enable_bridge_item(original)
        self.assertFalse(changed)
        self.assertEqual(updated, original)

    def test_other_plugin_selection_is_not_overwritten(self) -> None:
        original = b"plugin_display_item=other.plugin.item\n"
        with self.assertRaisesRegex(ValueError, "other entries"):
            enable_bridge_item(original)

    def test_marked_staging_copy_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            (stage / "TrafficMonitor.exe").write_bytes(b"test executable")
            (stage / BRIDGE_DLL).parent.mkdir(parents=True)
            (stage / BRIDGE_DLL).write_bytes(b"test bridge")
            (stage / "config.ini").write_bytes(b"plugin_display_item=\n")
            with self.assertRaisesRegex(ValueError, "not marked"):
                configure_staged_copy(stage)

    def test_marked_copy_updates_only_its_own_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            (stage / "TrafficMonitor.exe").write_bytes(b"test executable")
            (stage / BRIDGE_DLL).parent.mkdir(parents=True)
            (stage / BRIDGE_DLL).write_bytes(b"test bridge")
            (stage / STAGE_MARKER).write_bytes(STAGE_MARKER_CONTENT)
            config = stage / "config.ini"
            config.write_bytes(b"plugin_display_item=\nother=value\n")
            self.assertTrue(configure_staged_copy(stage))
            self.assertEqual(
                config.read_bytes(), b"plugin_display_item=wincraft.bridge\nother=value\n"
            )

    def test_fresh_marked_copy_creates_only_a_temporary_bridge_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            (stage / "TrafficMonitor.exe").write_bytes(b"test executable")
            (stage / BRIDGE_DLL).parent.mkdir(parents=True)
            (stage / BRIDGE_DLL).write_bytes(b"test bridge")
            (stage / STAGE_MARKER).write_bytes(STAGE_MARKER_CONTENT)

            with self.assertRaisesRegex(ValueError, "config.ini is missing"):
                configure_staged_copy(stage)

            self.assertTrue(configure_staged_copy(stage, create_config_if_missing=True))
            self.assertEqual(
                (stage / "config.ini").read_bytes(),
                b"[config]\r\n"
                b"show_task_bar_wnd=true\r\n"
                b"plugin_disabled=\r\n"
                b"[task_bar]\r\n"
                b"plugin_display_item=wincraft.bridge\r\n",
            )


if __name__ == "__main__":
    unittest.main()
