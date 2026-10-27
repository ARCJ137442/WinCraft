import json
import tempfile
import unittest
from pathlib import Path

from examples.python.trafficmonitor_provider import make_view_data, read_metrics


class TrafficMonitorProviderTests(unittest.TestCase):
    def test_missing_file_is_waiting_not_zero(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(read_metrics(Path(folder) / "metrics.json"))
        view = make_view_data(None, now_ms=1_800_000_000_000)
        self.assertEqual(view["status"], "等待 TrafficMonitor")
        self.assertEqual(view["download"], "—")

    def test_valid_local_snapshot_and_zero_are_preserved(self) -> None:
        payload = {
            "schema": "wincraft.trafficmonitor.v1",
            "sampled_at_ms": 1_800_000_000_000,
            "generation": 9,
            "app_version": "1.8.6.0",
            "download": "0 KB/s",
            "upload": "1 KB/s",
            "cpu": "4%",
            "memory": "37%",
            "gpu": None,
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "metrics.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            snapshot = read_metrics(path)
        self.assertEqual(snapshot, payload)
        view = make_view_data(snapshot, now_ms=1_800_000_001_000)
        self.assertEqual(view["status"], "")
        self.assertEqual(view["download"], "0 KB/s")
        self.assertEqual(view["gpu"], "—")

    def test_invalid_snapshot_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "metrics.json"
            path.write_text('{"schema":"wrong"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_metrics(path)

    def test_stale_and_source_error_keep_last_readings(self) -> None:
        snapshot = {
            "schema": "wincraft.trafficmonitor.v1",
            "sampled_at_ms": 1_800_000_000_000,
            "generation": 9,
            "app_version": "1.8.6.0",
            "download": "12 KB/s",
            "upload": "3 KB/s",
            "cpu": "4%",
            "memory": "37%",
            "gpu": None,
        }
        stale = make_view_data(snapshot, now_ms=1_800_000_010_000)
        self.assertEqual(stale["status"], "数据已过期")
        self.assertEqual(stale["download"], "12 KB/s")
        invalid = make_view_data(snapshot, source_error="桥接文件无效", now_ms=1_800_000_002_000)
        self.assertEqual(invalid["status"], "桥接文件无效")
        self.assertEqual(invalid["download"], "12 KB/s")


if __name__ == "__main__":
    unittest.main()
