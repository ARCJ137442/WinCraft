'''使用合成 HTTP 响应验证 DeepSeek/MiniMax 只读适配器。'''
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

INTEGRATION_DIR = Path(__file__).resolve().parents[1] / 'examples' / 'integrations' / 'model_quota'
if str(INTEGRATION_DIR) not in sys.path:
    sys.path.insert(0, str(INTEGRATION_DIR))

import provider_sources  # noqa: E402
from provider_sources import (  # noqa: E402
    DEEPSEEK_BALANCE_URL,
    MINIMAX_QUOTA_URL,
    ProviderQuotaError,
    fetch_deepseek_balance,
    fetch_minimax_quota,
    refresh_local_sources,
)


SYNTHETIC_KEY = 'synthetic-provider-api-key-never-project'
SYNTHETIC_NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


class _Response:
    def __init__(self, body: bytes, *, status: int = 200) -> None:
        self.body = body
        self.status = status
        self.headers = {'Content-Length': str(len(body))}

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def read(self, limit: int) -> bytes:
        return self.body[:limit]


class _Opener:
    def __init__(self, response: _Response | Exception, captured: dict[str, Any]) -> None:
        self.response = response
        self.captured = captured

    def open(self, request, timeout: float) -> _Response:
        self.captured['url'] = request.full_url
        self.captured['method'] = request.get_method()
        self.captured['headers'] = {
            name.casefold(): value for name, value in request.header_items()
        }
        self.captured['timeout'] = timeout
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _factory_for(response: _Response | Exception, captured: dict[str, Any]):
    def opener_factory(*_handlers: object) -> _Opener:
        return _Opener(response, captured)

    return opener_factory


def _minimax_response() -> dict[str, Any]:
    return {
        'base_resp': {'status_code': 0},
        'model_remains': [
            {
                'model_name': 'MiniMax-M2',
                'current_interval_status': 1,
                'current_interval_remaining_percent': 35,
                'current_interval_total_count': 100,
                'current_interval_usage_count': 65,
                'start_time': 1_798_000_000,
                'end_time': 1_798_003_600,
                'current_weekly_status': 1,
                'current_weekly_remaining_percent': 60,
                'current_weekly_total_count': 100,
                'current_weekly_usage_count': 40,
                'weekly_start_time': 1_798_000_000,
                'weekly_end_time': 1_798_604_800,
            },
        ],
    }


class ProviderQuotaSourceTests(unittest.TestCase):
    def test_given_deepseek_fixed_get_when_response_is_valid_then_only_currency_balances_remain(
        self,
    ) -> None:
        body = json.dumps(
            {
                'is_available': True,
                'balance_infos': [
                    {
                        'currency': 'CNY',
                        'total_balance': '1.250001',
                        'granted_balance': '0.500000',
                        'topped_up_balance': '0.750001',
                    },
                ],
                'account_id': 'synthetic-private-account',
            }
        ).encode()
        captured: dict[str, Any] = {}

        projection = fetch_deepseek_balance(
            SYNTHETIC_KEY,
            opener_factory=_factory_for(_Response(body), captured),
            now=SYNTHETIC_NOW,
        )

        self.assertEqual(captured['url'], DEEPSEEK_BALANCE_URL)
        self.assertEqual(captured['method'], 'GET')
        self.assertEqual(captured['headers']['authorization'], f'Bearer {SYNTHETIC_KEY}')
        self.assertLessEqual(captured['timeout'], provider_sources.REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(projection['balance']['balances'][0]['totalMicros'], 1_250_001)
        self.assertEqual(projection['meta']['freshness'], 'fresh')
        serialized = json.dumps(projection)
        self.assertNotIn(SYNTHETIC_KEY, serialized)
        self.assertNotIn('synthetic-private-account', serialized)

    def test_given_minimax_fixed_get_when_response_is_valid_then_model_windows_remain_independent(
        self,
    ) -> None:
        body = json.dumps(_minimax_response()).encode()
        captured: dict[str, Any] = {}

        projection = fetch_minimax_quota(
            SYNTHETIC_KEY,
            opener_factory=_factory_for(_Response(body), captured),
            now=SYNTHETIC_NOW,
        )

        self.assertEqual(captured['url'], MINIMAX_QUOTA_URL)
        self.assertEqual(captured['method'], 'GET')
        self.assertEqual(captured['headers']['authorization'], f'Bearer {SYNTHETIC_KEY}')
        self.assertEqual(captured['headers']['content-type'], 'application/json')
        self.assertEqual(len(projection['quota']['models']), 1)
        model = projection['quota']['models'][0]
        self.assertEqual(model['interval']['remainingPercent'], 35)
        self.assertEqual(model['weekly']['remainingPercent'], 60)
        self.assertEqual(model['interval']['remainingCount'], 35)
        self.assertEqual(projection['meta']['upstreamState'], 'healthy')
        self.assertNotIn(SYNTHETIC_KEY, json.dumps(projection))

    def test_minimax_cap_reports_omitted_models(self) -> None:
        payload = _minimax_response()
        model = payload['model_remains'][0]
        payload['model_remains'] = [
            {**model, 'model_name': f'MiniMax-M{index}'}
            for index in range(provider_sources.MAX_MODELS + 2)
        ]
        body = json.dumps(payload).encode()

        projection = fetch_minimax_quota(
            SYNTHETIC_KEY,
            opener_factory=_factory_for(_Response(body), {}),
            now=SYNTHETIC_NOW,
        )

        self.assertEqual(len(projection['quota']['models']), provider_sources.MAX_MODELS)
        self.assertEqual(projection['quota']['omittedModelCount'], 2)

    def test_given_unexpected_redirect_when_supplier_responds_then_redirect_is_not_followed(
        self,
    ) -> None:
        captured: dict[str, Any] = {}
        with self.assertRaises(ProviderQuotaError) as raised:
            fetch_minimax_quota(
                SYNTHETIC_KEY,
                opener_factory=_factory_for(_Response(b'{}', status=302), captured),
                now=SYNTHETIC_NOW,
            )

        self.assertEqual(raised.exception.code, 'REDIRECT_BLOCKED')
        self.assertEqual(captured['url'], MINIMAX_QUOTA_URL)

    def test_given_oversized_supplier_response_when_read_then_body_is_rejected(self) -> None:
        body = b' ' * (provider_sources.MAX_RESPONSE_BYTES + 1)
        with self.assertRaises(ProviderQuotaError) as raised:
            fetch_deepseek_balance(
                SYNTHETIC_KEY,
                opener_factory=_factory_for(_Response(body), {}),
                now=SYNTHETIC_NOW,
            )

        self.assertEqual(raised.exception.code, 'RESPONSE_TOO_LARGE')

    def test_given_sources_disabled_when_refresh_runs_then_no_key_environment_variable_is_read(
        self,
    ) -> None:
        class _NoReadEnvironment(dict[str, str]):
            def get(self, key: str, default: str | None = None) -> str | None:
                raise AssertionError(f'unexpected environment access: {key}')

        projection = refresh_local_sources(
            deepseek_enabled=False,
            minimax_enabled=False,
            previous=None,
            environment=_NoReadEnvironment(),
        )

        self.assertEqual(projection['sources'], [])
        self.assertEqual(projection['deepseek']['meta']['errorCode'], 'NOT_ENABLED')
        self.assertEqual(projection['minimax']['meta']['errorCode'], 'NOT_ENABLED')

    def test_given_enabled_source_without_key_when_refresh_runs_then_network_is_not_touched(
        self,
    ) -> None:
        with patch.object(provider_sources.urllib.request, 'build_opener') as build_opener:
            projection = refresh_local_sources(
                deepseek_enabled=True,
                minimax_enabled=False,
                previous=None,
                environment={},
            )

        build_opener.assert_not_called()
        self.assertEqual(projection['deepseek']['meta']['errorCode'], 'NOT_CONFIGURED')

    def test_network_failure_retains_last_good_as_stale(self) -> None:
        previous = {
            'deepseek': {
                'balance': {
                    'isAvailable': True,
                    'balances': [{'currency': 'CNY', 'totalMicros': 100}],
                },
                'meta': {
                    'freshness': 'fresh',
                    'upstreamState': 'healthy',
                    'fetchedAt': '2026-10-31T11:00:00Z',
                },
            },
            'minimax': {'quota': None, 'meta': {'errorCode': 'NOT_ENABLED'}},
        }
        captured: dict[str, Any] = {}
        failing_factory = _factory_for(OSError('synthetic private socket detail'), captured)

        projection = refresh_local_sources(
            deepseek_enabled=True,
            minimax_enabled=False,
            previous=previous,
            environment={provider_sources.DEEPSEEK_API_KEY_ENV: SYNTHETIC_KEY},
            opener_factory=failing_factory,
            now=SYNTHETIC_NOW,
        )

        self.assertEqual(projection['deepseek']['meta']['freshness'], 'stale')
        self.assertEqual(projection['deepseek']['meta']['upstreamState'], 'offline')
        self.assertEqual(projection['deepseek']['balance'], previous['deepseek']['balance'])
        self.assertEqual(projection['deepseek']['meta']['errorCode'], 'NETWORK_ERROR')
        self.assertNotIn('synthetic private socket detail', repr(projection))
        self.assertNotIn(SYNTHETIC_KEY, repr(projection))


if __name__ == '__main__':
    unittest.main()
