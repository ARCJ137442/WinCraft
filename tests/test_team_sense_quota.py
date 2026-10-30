"""Given a synthetic TeamSense cache, the quota panel preserves source and window truth."""
from __future__ import annotations

import sys
import unittest
import json
from unittest.mock import patch
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parents[1] / "examples" / "integrations" / "model_quota"
if str(INTEGRATION_DIR) not in sys.path:
    sys.path.insert(0, str(INTEGRATION_DIR))

from team_sense_quota import (  # noqa: E402
    build_quota_scene,
    fetch_team_sense_models,
    normalize_models_snapshot,
    quota_window_spec,
    validate_base_url,
    with_api_read_state,
)


def synthetic_snapshot() -> dict:
    return {
        "deepseek": {
            "balance": {
                "fetchedAt": "2026-10-30T02:00:00Z",
                "isAvailable": True,
                "balances": [
                    {"currency": "CNY", "totalMicros": 1_250_000, "grantedMicros": 500_000,
                     "toppedUpMicros": 750_000},
                    {"currency": "USD", "totalMicros": 0, "grantedMicros": 0,
                     "toppedUpMicros": 0},
                ],
            },
            "meta": {
                "sourceKey": "deepseek", "freshness": "fresh", "upstreamState": "healthy",
                "fetchedAt": "2026-10-30T02:00:00Z", "lastSuccessAt": "2026-10-30T02:00:00Z",
            },
        },
        "minimax": {
            "quota": {
                "fetchedAt": "2026-10-30T01:59:00Z",
                "isAvailable": True,
                "models": [
                    {
                        "key": "model-a", "name": "Model A",
                        "interval": {
                            "state": "metered", "windowSeconds": 3600,
                            "remainingPercent": 25, "usedCount": 75, "remainingCount": 25,
                            "totalCount": 100, "resetsAt": "2026-10-30T03:00:00Z",
                        },
                        "weekly": {
                            "state": "metered", "windowSeconds": 604800,
                            "remainingPercent": 80, "usedCount": 20, "remainingCount": 80,
                            "totalCount": 100, "resetsAt": "2026-11-01T00:00:00Z",
                        },
                    },
                ],
            },
            "meta": {
                "sourceKey": "minimax", "freshness": "stale", "upstreamState": "degraded",
                "fetchedAt": "2026-10-30T01:59:00Z", "lastSuccessAt": "2026-10-30T01:59:00Z",
            },
        },
        "sub2api": {
            "management": {"configured": True},
            "meta": {
                "sourceKey": "sub2api", "freshness": "empty", "upstreamState": "unknown",
                "fetchedAt": None, "lastSuccessAt": None,
            },
        },
    }


class TeamSenseQuotaProjectionTests(unittest.TestCase):
    def test_given_cached_model_data_when_projected_then_currency_and_model_windows_stay_separate(self):
        projection = normalize_models_snapshot(
            synthetic_snapshot(), api_connected=True, api_observed_at="2026-10-30T02:01:00Z"
        )

        self.assertEqual(
            [(item["currency"], item["display"]) for item in projection["deepseek"]["balances"]],
            [("CNY", "¥1.25"), ("USD", "$0.00")],
        )
        self.assertEqual(
            [(item["model"], item["window"], item["value"], item["maximum"])
             for item in projection["minimax"]["windows"]],
            [
                ("Model A", "当前周期", 25, 100),
                ("Model A", "周周期", 80, 100),
            ],
        )
        self.assertEqual(projection["identity_scope"], "当前 TeamSense 连接；接口未返回账户标识")

    def test_given_zero_and_missing_fields_when_projected_then_zero_is_not_missing(self):
        payload = synthetic_snapshot()
        payload["deepseek"]["balance"]["balances"][1]["totalMicros"] = 0
        payload["minimax"]["quota"]["models"][0]["interval"]["remainingPercent"] = None
        payload["minimax"]["quota"]["models"][0]["interval"]["remainingCount"] = None
        payload["minimax"]["quota"]["models"][0]["interval"]["totalCount"] = None

        projection = normalize_models_snapshot(payload, api_connected=True)

        self.assertEqual(projection["deepseek"]["balances"][1]["display"], "$0.00")
        self.assertIsNone(projection["minimax"]["windows"][0]["value"])
        self.assertIsNone(projection["minimax"]["windows"][0]["maximum"])
        self.assertEqual(projection["minimax"]["windows"][0]["status_label"], "额度未知")

    def test_given_unlimited_state_and_residual_meter_when_projected_then_state_wins(self):
        payload = synthetic_snapshot()
        payload["minimax"]["quota"]["models"][0]["interval"].update(
            {"state": "unlimited", "remainingPercent": 80}
        )

        projection = normalize_models_snapshot(payload, api_connected=True)

        self.assertEqual(projection["minimax"]["windows"][0]["status_label"], "不限量")
        self.assertIsNone(projection["minimax"]["windows"][0]["value"])
        self.assertIsNone(projection["minimax"]["windows"][0]["maximum"])

    def test_given_more_models_than_the_panel_limit_when_projected_then_omission_is_disclosed(self):
        payload = synthetic_snapshot()
        model = payload["minimax"]["quota"]["models"][0]
        payload["minimax"]["quota"]["models"] = [
            {**model, "key": f"model-{index}", "name": f"Model {index}"}
            for index in range(10)
        ]

        projection = normalize_models_snapshot(payload, api_connected=True)
        scene = build_quota_scene(projection)
        ids = []

        def visit(node):
            ids.append(node["id"])
            for child in node.get("children", []):
                visit(child)

        visit(scene["root"])
        self.assertEqual(len(projection["minimax"]["windows"]), 16)
        self.assertEqual(projection["minimax"]["omitted_model_count"], 2)
        self.assertIn("quota-minimax-omitted-models", ids)

    def test_given_stale_source_and_failed_api_read_when_projected_then_freshness_and_connectivity_are_distinct(self):
        projection = normalize_models_snapshot(
            synthetic_snapshot(), api_connected=False, api_observed_at="2026-10-30T02:02:00Z"
        )

        self.assertEqual(projection["api"]["state_label"], "TeamSense API 不可达")
        self.assertEqual(projection["minimax"]["freshness_label"], "陈旧")
        self.assertEqual(projection["minimax"]["upstream_label"], "来源降级")
        self.assertEqual(len(projection["minimax"]["windows"]), 2)
        self.assertEqual(projection["deepseek"]["freshness_label"], "新鲜")

    def test_given_last_good_projection_when_http_read_fails_then_values_remain_but_api_is_offline(self):
        last_good = normalize_models_snapshot(synthetic_snapshot(), api_connected=True)
        disconnected = with_api_read_state(
            last_good,
            api_connected=False,
            api_observed_at="2026-10-30T02:02:00Z",
            api_error_code="HTTP_403",
        )

        self.assertEqual(disconnected["api"]["state_label"], "TeamSense API 不可达")
        self.assertEqual(disconnected["api"]["detail"], "token 缺少 data:read 权限")
        self.assertEqual(disconnected["minimax"]["freshness_label"], "陈旧")
        self.assertEqual(disconnected["minimax"]["windows"], last_good["minimax"]["windows"])
        self.assertEqual(disconnected["deepseek"]["balances"], last_good["deepseek"]["balances"])

    def test_given_no_codex_quota_in_read_api_when_projected_then_codex_remains_unknown(self):
        projection = normalize_models_snapshot(synthetic_snapshot(), api_connected=True)

        self.assertEqual(projection["codex"]["state_label"], "未知")
        self.assertIn("此只读接口未提供", projection["codex"]["detail"])
        self.assertNotIn("codex", projection["sources"])

    def test_given_extra_account_and_management_fields_when_projected_then_only_display_fields_remain(self):
        payload = synthetic_snapshot()
        payload["deepseek"]["accountId"] = "synthetic-private-account"
        payload["minimax"]["quota"]["accountId"] = "synthetic-private-account"
        payload["sub2api"]["management"] = {"credential": "synthetic-secret", "adminUrl": "private"}
        payload["connections"] = {"deepseek": {"accountId": "synthetic-private-account"}}

        projection = normalize_models_snapshot(payload, api_connected=True)
        encoded_projection = json.dumps(projection, ensure_ascii=False)

        self.assertNotIn("synthetic-private-account", encoded_projection)
        self.assertNotIn("synthetic-secret", encoded_projection)
        self.assertNotIn("adminUrl", encoded_projection)

    def test_given_projection_when_scene_is_built_then_progress_bars_and_unknown_states_are_visible(self):
        projection = normalize_models_snapshot(synthetic_snapshot(), api_connected=True)
        scene = build_quota_scene(projection)

        self.assertEqual(scene["theme"]["background"], "#1A1820")
        self.assertEqual(scene["theme"]["accent"], "#C4B5FD")
        self.assertFalse(quota_window_spec()["text_selectable"])
        self.assertIn("合成演示", quota_window_spec(demo=True)["title"])
        kinds = []

        def visit(node):
            kinds.append(node["kind"])
            for child in node.get("children", []):
                visit(child)

        visit(scene["root"])
        self.assertEqual(kinds.count("progress"), 2)
        self.assertIn("metric", kinds)
        self.assertGreaterEqual(kinds.count("badge"), 3)
        self.assertIn("identity_scope", scene["data"])
        self.assertEqual(scene["data"]["codex"]["state_label"], "未知")

    def test_given_http_endpoint_when_validated_then_only_loopback_is_permitted_without_tls(self):
        self.assertEqual(validate_base_url("http://127.0.0.1:8787"), "http://127.0.0.1:8787")
        self.assertEqual(validate_base_url("https://api.example.test"), "https://api.example.test")
        for url in (
            "http://api.example.test",
            "https://user:secret@api.example.test",
            "https://api.example.test/path",
            "https://api.example.test/?token=secret",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_base_url(url)

    def test_given_live_reader_when_called_then_it_uses_only_fixed_get_path_and_never_redirects(self):
        body = b'{"deepseek":{"balance":null,"meta":{}},"minimax":{"quota":null,"meta":{}},"sub2api":{"management":null,"meta":{}}}'
        captured = {}

        class FakeResponse:
            status = 200
            headers = {"Content-Length": str(len(body))}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return body

        class FakeOpener:
            def open(self, request, timeout):
                captured["url"] = request.full_url
                captured["method"] = request.get_method()
                captured["authorization"] = request.get_header("Authorization")
                captured["timeout"] = timeout
                return FakeResponse()

        with patch("team_sense_quota.urllib.request.build_opener", return_value=FakeOpener()):
            fetch_team_sense_models("https://api.example.test", "synthetic-token")

        self.assertEqual(captured["url"], "https://api.example.test/v1/integrations/models")
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["authorization"], "Bearer synthetic-token")
        self.assertNotIn("synthetic-token", captured["url"])
        self.assertLessEqual(captured["timeout"], 6)
        self.assertIsNone(__import__("team_sense_quota")._NoRedirectHandler().redirect_request(
            None, None, 302, "Found", {}, "https://other.example.test/"
        ))


if __name__ == "__main__":
    unittest.main()
