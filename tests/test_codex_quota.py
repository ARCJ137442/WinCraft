"""Given synthetic Codex auth and usage data, the opt-in quota adapter stays bounded and read-only."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

INTEGRATION_DIR = Path(__file__).resolve().parents[1] / "examples" / "integrations" / "model_quota"
if str(INTEGRATION_DIR) not in sys.path:
    sys.path.insert(0, str(INTEGRATION_DIR))

import codex_quota  # noqa: E402
from team_sense_quota import build_quota_scene, normalize_models_snapshot  # noqa: E402


SYNTHETIC_TOKEN = "synthetic-access-token-never-send"
SYNTHETIC_ACCOUNT = "synthetic-codex-account-never-display"
SYNTHETIC_RESPONSE = {
    "rate_limit": {
        "primary_window": {
            "used_percent": 35,
            "limit_window_seconds": 18_000,
            "reset_at": 1_800_000_000,
        },
        "secondary_window": {
            "used_percent": 68,
            "limit_window_seconds": 604_800,
            "reset_at": 1_800_604_800,
        },
    },
    "plan_type": "synthetic-plan-label-not-projected",
    "credits": {"balance": "synthetic-credit-balance-not-projected"},
}


class CodexQuotaTests(unittest.TestCase):
    def _write_auth(self, root: Path, account_id: str = SYNTHETIC_ACCOUNT) -> Path:
        auth_file = root / "auth.json"
        auth_file.write_text(
            json.dumps(
                {
                    "tokens": {
                        "access_token": SYNTHETIC_TOKEN,
                        "account_id": account_id,
                        "refresh_token": "synthetic-refresh-token-must-not-be-used",
                    },
                    "other_private_field": "must-not-be-projected",
                }
            ),
            encoding="utf-8",
        )
        return auth_file

    def _response(self, body: bytes | None = None):
        encoded = json.dumps(SYNTHETIC_RESPONSE).encode() if body is None else body

        class FakeResponse:
            status = 200
            headers = {"Content-Length": str(len(encoded))}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, limit: int) -> bytes:
                return encoded[:limit]

        return FakeResponse()

    def test_given_opt_in_credentials_when_get_succeeds_then_only_bounded_quota_windows_are_projected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_auth(root)
            captured: dict[str, object] = {}

            class FakeOpener:
                def open(self, request, timeout):
                    headers = {name.casefold(): value for name, value in request.header_items()}
                    captured["url"] = request.full_url
                    captured["method"] = request.get_method()
                    captured["authorization"] = request.get_header("Authorization")
                    captured["account"] = headers.get("chatgpt-account-id")
                    captured["timeout"] = timeout
                    return self_outer._response()

            self_outer = self
            with patch.object(codex_quota.urllib.request, "build_opener", return_value=FakeOpener()):
                projection = codex_quota.fetch_codex_quota(root)

        self.assertEqual(captured["url"], codex_quota.CODEX_USAGE_ENDPOINT)
        self.assertEqual(captured["method"], "GET")
        self.assertEqual(captured["authorization"], f"Bearer {SYNTHETIC_TOKEN}")
        self.assertEqual(captured["account"], SYNTHETIC_ACCOUNT)
        self.assertLessEqual(captured["timeout"], codex_quota.REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(len(projection["windows"]), 2)
        self.assertEqual(projection["windows"][0]["remaining_percent"], 65.0)
        self.assertEqual(projection["windows"][1]["window_seconds"], 604_800)
        self.assertIn("周周期", projection["windows"][1]["label"])
        serialized = json.dumps(projection, ensure_ascii=False)
        for private_value in (SYNTHETIC_TOKEN, SYNTHETIC_ACCOUNT, "synthetic-refresh-token", "synthetic-credit"):
            self.assertNotIn(private_value, serialized)

    def test_given_codex_file_when_loaded_then_credentials_are_not_represented_or_logged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_auth(root)
            credentials = codex_quota._load_auth_credentials(root / "auth.json")

        self.assertNotIn(SYNTHETIC_TOKEN, repr(credentials))
        self.assertNotIn(SYNTHETIC_ACCOUNT, repr(credentials))

    def test_given_codex_source_disabled_when_projection_refreshes_then_no_credentials_or_network_are_touched(self):
        with patch.object(codex_quota, "fetch_codex_quota") as codex_fetch:
            projection = codex_quota.refresh_codex_source(
                enabled=False,
                explicit_home=None,
                previous=None,
            )

        codex_fetch.assert_not_called()
        self.assertEqual(projection["state_label"], "未启用")
        self.assertEqual(projection["windows"], [])

    def test_given_account_switch_during_get_when_response_arrives_then_old_quota_is_discarded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            auth_file = self._write_auth(root)

            class SwitchingResponse(self._response().__class__):
                def read(self, limit: int) -> bytes:
                    self_outer._write_auth(root, "different-synthetic-account")
                    return super().read(limit)

            class FakeOpener:
                def open(self, _request, timeout):
                    return SwitchingResponse()

            self_outer = self
            with patch.object(codex_quota.urllib.request, "build_opener", return_value=FakeOpener()):
                with self.assertRaises(codex_quota.CodexQuotaError) as raised:
                    codex_quota.fetch_codex_quota(root)
            updated_auth = json.loads(auth_file.read_text(encoding="utf-8"))
            self.assertEqual(updated_auth["tokens"]["account_id"], "different-synthetic-account")

        self.assertEqual(raised.exception.code, "ACCOUNT_CHANGED")
        self.assertNotIn(SYNTHETIC_ACCOUNT, str(raised.exception))

    def test_given_auth_file_exceeds_bound_when_enabled_then_no_network_opener_is_created(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "auth.json").write_bytes(b"{" + b" " * codex_quota.MAX_AUTH_BYTES + b"}")
            with patch.object(codex_quota.urllib.request, "build_opener") as opener:
                with self.assertRaises(codex_quota.CodexQuotaError) as raised:
                    codex_quota.fetch_codex_quota(root)

        self.assertEqual(raised.exception.code, "AUTH_FILE_INVALID")
        opener.assert_not_called()

    def test_given_redirecting_upstream_when_requested_then_bearer_redirect_is_refused(self):
        handler = codex_quota._NoRedirectHandler()

        self.assertIsNone(
            handler.redirect_request(
                None,
                None,
                302,
                "Found",
                {},
                "https://other.example.test/",
            )
        )

    def test_given_invalid_primary_window_when_parsed_then_unknown_is_not_zero(self):
        with self.assertRaises(codex_quota.CodexQuotaError) as raised:
            codex_quota.normalize_codex_usage(
                {"rate_limit": {"primary_window": {"used_percent": None}}},
                observed_at="2026-10-31T00:00:00Z",
            )

        self.assertEqual(raised.exception.code, "PRIMARY_WINDOW_INVALID")

    def test_given_extreme_or_zero_reset_fields_when_parsed_then_values_fail_closed(self):
        extreme = json.loads(json.dumps(SYNTHETIC_RESPONSE))
        extreme["rate_limit"]["primary_window"]["used_percent"] = 10**1_000
        zero_reset = json.loads(json.dumps(SYNTHETIC_RESPONSE))
        zero_reset["rate_limit"]["primary_window"]["reset_at"] = 0

        for payload in (extreme, zero_reset):
            with self.subTest(payload=payload["rate_limit"]["primary_window"]):
                with self.assertRaises(codex_quota.CodexQuotaError) as raised:
                    codex_quota.normalize_codex_usage(
                        payload,
                        observed_at="2026-10-31T00:00:00Z",
                    )
                self.assertEqual(raised.exception.code, "PRIMARY_WINDOW_INVALID")

    def test_given_last_good_codex_quota_when_network_fails_then_keep_it_marked_failed_but_clear_on_account_change(self):
        last_good = codex_quota.normalize_codex_usage(
            SYNTHETIC_RESPONSE,
            observed_at="2026-10-31T00:00:00Z",
        )

        disconnected = codex_quota.with_codex_read_error(last_good, "NETWORK_ERROR")
        changed_account = codex_quota.with_codex_read_error(last_good, "ACCOUNT_CHANGED")

        self.assertEqual(disconnected["state_label"], "读取失败")
        self.assertEqual(disconnected["windows"], last_good["windows"])
        self.assertIsNone(changed_account["observed_at"])
        self.assertEqual(changed_account["windows"], [])
        self.assertIn("账号状态不明确", changed_account["observed_label"])

    def test_given_disabled_codex_source_when_scene_is_built_then_state_is_explicit_and_unknown(self):
        projection = normalize_models_snapshot({}, api_connected=False, api_error_code="NOT_CONFIGURED")
        scene = build_quota_scene(projection)
        codex = scene["data"]["codex"]
        self.assertEqual(codex["state_label"], "未启用")
        self.assertEqual(codex["windows"], [])
        self.assertIn("会话历史推算", codex["detail"])

    def test_given_codex_quota_windows_when_scene_is_built_then_remaining_percent_uses_progress_bars(self):
        projection = normalize_models_snapshot({}, api_connected=False, api_error_code="NOT_CONFIGURED")
        projection["codex"] = codex_quota.normalize_codex_usage(
            SYNTHETIC_RESPONSE,
            observed_at="2026-10-31T00:00:00Z",
        )
        scene = build_quota_scene(projection)
        nodes: list[dict[str, object]] = []

        def visit(node):
            nodes.append(node)
            for child in node.get("children", []):
                visit(child)

        visit(scene["root"])
        codex_bars = [
            node
            for node in nodes
            if node["kind"] == "progress" and str(node["id"]).startswith("quota-codex-window-")
        ]
        self.assertEqual(len(codex_bars), 2)
        self.assertIn("quota-codex-freshness", [node["id"] for node in nodes])
        self.assertEqual(scene["data"]["codex"]["windows"][0]["value"], 65.0)


if __name__ == "__main__":
    unittest.main()
