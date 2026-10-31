'''给定合成 Codex rollout，检查 quota 事件只读投影与扫描上限。'''
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parents[1] / 'examples' / 'integrations' / 'model_quota'
if str(INTEGRATION_DIR) not in sys.path:
    sys.path.insert(0, str(INTEGRATION_DIR))

from codex_rollout_quota import (  # noqa: E402
    read_latest_codex_rollout_quota,
    refresh_codex_rollout_source,
)
from quota_projection import build_quota_scene  # noqa: E402

PROVIDER_SPEC = importlib.util.spec_from_file_location(
    'model_quota_provider_under_test',
    INTEGRATION_DIR / 'provider.py',
)
assert PROVIDER_SPEC is not None and PROVIDER_SPEC.loader is not None
provider = importlib.util.module_from_spec(PROVIDER_SPEC)
sys.modules[PROVIDER_SPEC.name] = provider
PROVIDER_SPEC.loader.exec_module(provider)


NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
SYNTHETIC_EVENT = {
    'timestamp': '2026-10-31T11:59:00Z',
    'type': 'event_msg',
    'thread_id': 'synthetic-thread-id',
    'ordinal': 4,
    'payload': {
        'type': 'token_count',
        'info': {
            'last_token_usage': {'output_tokens': 999, 'tool_output': 'must-not-project'},
            'conversation_text': 'synthetic sensitive body; must-not-project',
        },
        'rate_limits': {
            'limit_id': 'codex',
            'primary': {
                'used_percent': 25,
                'window_minutes': 300,
                'resets_at': 1_798_000_000,
            },
            'secondary': {
                'used_percent': 60,
                'window_minutes': 10_080,
                'resets_at': 1_798_500_000,
            },
            'credits': {'balance': 'must-not-project'},
        },
    },
}


class CodexRolloutQuotaTests(unittest.TestCase):
    def _write_event(self, root: Path, relative: str, event: dict[str, object]) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(event), encoding='utf-8')
        return path

    def test_given_token_count_rollout_when_read_then_only_quota_fields_are_projected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_event(root, 'sessions/2026/10/31/rollout-a.jsonl', SYNTHETIC_EVENT)
            projection = read_latest_codex_rollout_quota(root, now=NOW)

        assert projection is not None
        self.assertEqual(projection['state_label'], '本机快照')
        self.assertEqual(projection['freshness_label'], '新鲜')
        self.assertEqual(projection['observed_at'], '2026-10-31T11:59:00Z')
        self.assertEqual(len(projection['windows']), 2)
        self.assertEqual(projection['windows'][0]['remaining_percent'], 75.0)
        self.assertEqual(projection['windows'][1]['window_seconds'], 604_800)
        serialized = json.dumps(projection, ensure_ascii=False)
        for private_value in (
            'synthetic-thread-id',
            'synthetic sensitive body',
            'must-not-project',
            'conversation_text',
        ):
            self.assertNotIn(private_value, serialized)

    def test_given_multiple_session_files_when_read_then_latest_event_time_wins(self) -> None:
        old_event = json.loads(json.dumps(SYNTHETIC_EVENT))
        old_event['timestamp'] = '2026-10-31T11:30:00Z'
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_event(root, 'sessions/2026/10/31/rollout-old.jsonl', SYNTHETIC_EVENT)
            self._write_event(root, 'archived_sessions/2026/10/31/rollout-new.jsonl', old_event)
            newest_event = json.loads(json.dumps(SYNTHETIC_EVENT))
            newest_event['timestamp'] = '2026-10-31T11:59:30Z'
            self._write_event(root, 'sessions/2026/10/31/rollout-newest.jsonl', newest_event)
            projection = read_latest_codex_rollout_quota(root, now=NOW)

        assert projection is not None
        self.assertEqual(projection['observed_at'], '2026-10-31T11:59:30Z')

    def test_given_expired_event_when_read_then_value_remains_marked_expired(self) -> None:
        old_event = json.loads(json.dumps(SYNTHETIC_EVENT))
        old_event['timestamp'] = '2026-10-31T09:00:00Z'
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_event(root, 'sessions/2026/10/31/rollout-old.jsonl', old_event)
            projection = read_latest_codex_rollout_quota(root, now=NOW)

        assert projection is not None
        self.assertEqual(projection['freshness_label'], '已过期')
        self.assertIsNotNone(projection['windows'][0]['value'])

    def test_given_non_quota_or_invalid_event_when_read_then_no_quota_is_invented(self) -> None:
        invalid_event = json.loads(json.dumps(SYNTHETIC_EVENT))
        invalid_event['payload']['rate_limits']['primary']['used_percent'] = 101
        non_quota_event = {
            'timestamp': '2026-10-31T11:59:30Z',
            'type': 'event_msg',
            'payload': {'type': 'agent_message', 'message': 'must-not-project'},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'sessions/2026/10/31/rollout.jsonl'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                '\n'.join(json.dumps(event) for event in (invalid_event, non_quota_event)),
                encoding='utf-8',
            )
            projection = read_latest_codex_rollout_quota(root, now=NOW)

        self.assertIsNone(projection)

    def test_given_future_or_malformed_timestamp_when_read_then_event_is_ignored(self) -> None:
        invalid_events = []
        for timestamp in ('2026-10-31T13:00:00Z', 'not-a-timestamp'):
            event = json.loads(json.dumps(SYNTHETIC_EVENT))
            event['timestamp'] = timestamp
            invalid_events.append(event)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'sessions/2026/10/31/rollout.jsonl'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                '\n'.join(json.dumps(event) for event in invalid_events),
                encoding='utf-8',
            )
            projection = read_latest_codex_rollout_quota(root, now=NOW)

        self.assertIsNone(projection)

    def test_given_missing_rollout_directory_when_enabled_then_state_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            projection = refresh_codex_rollout_source(
                enabled=True,
                explicit_home=Path(temporary),
                previous=None,
                now=NOW,
            )

        self.assertEqual(projection['state_label'], '未找到 Codex rollout 目录')
        self.assertEqual(projection['windows'], [])

    def test_given_disabled_source_when_refreshed_then_codex_home_is_not_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            projection = refresh_codex_rollout_source(
                enabled=False,
                explicit_home=Path(temporary),
                previous=None,
                now=NOW,
            )

        self.assertEqual(projection['state_label'], '未启用')
        self.assertEqual(projection['windows'], [])

    def test_synthetic_rollout_refresh_builds_redacted_scene(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_event(root, 'sessions/2026/10/31/rollout-a.jsonl', SYNTHETIC_EVENT)
            projection, source_snapshots = asyncio.run(
                getattr(provider, '__refresh_sources')(
                    codex_enabled=False,
                    codex_rollout_enabled=True,
                    codex_home=root,
                    deepseek_enabled=False,
                    minimax_enabled=False,
                    previous=None,
                    previous_source_snapshots=None,
                    now=NOW,
                )
            )

        scene = build_quota_scene(projection)
        serialized = json.dumps(scene, ensure_ascii=False)
        self.assertEqual(projection['codex']['state_label'], '本机快照')
        self.assertIn('codex_rollout', projection['sources'])
        self.assertEqual(source_snapshots, {})
        self.assertNotIn('synthetic-thread-id', serialized)
        self.assertNotIn('synthetic sensitive body', serialized)
        self.assertNotIn('rate_limits', serialized)


if __name__ == '__main__':
    unittest.main()
