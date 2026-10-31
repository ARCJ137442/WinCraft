'''给定本机额度快照，检查来源边界、未知值与声明式面板场景。'''
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

INTEGRATION_DIR = Path(__file__).resolve().parents[1] / 'examples' / 'integrations' / 'model_quota'
if str(INTEGRATION_DIR) not in sys.path:
    sys.path.insert(0, str(INTEGRATION_DIR))

from quota_projection import (  # noqa: E402
    build_quota_scene,
    normalize_quota_snapshot,
    quota_window_spec,
    synthetic_demo_snapshot,
)


def synthetic_snapshot() -> dict[str, object]:
    '''建立不含真实账户、凭据或业务数据的额度来源 fixture。'''
    return {
        'deepseek': {
            'balance': {
                'fetchedAt': '2026-10-30T02:00:00Z',
                'isAvailable': True,
                'balances': [
                    {
                        'currency': 'CNY',
                        'totalMicros': 1_250_000,
                        'grantedMicros': 500_000,
                        'toppedUpMicros': 750_000,
                    },
                    {
                        'currency': 'USD',
                        'totalMicros': 0,
                        'grantedMicros': 0,
                        'toppedUpMicros': 0,
                    },
                ],
            },
            'meta': {
                'freshness': 'fresh',
                'upstreamState': 'healthy',
                'fetchedAt': '2026-10-30T02:00:00Z',
            },
        },
        'minimax': {
            'quota': {
                'fetchedAt': '2026-10-30T01:59:00Z',
                'isAvailable': True,
                'models': [
                    {
                        'key': 'synthetic-model-a',
                        'name': 'Model A',
                        'interval': {
                            'state': 'metered',
                            'windowSeconds': 3600,
                            'remainingPercent': 25,
                            'usedCount': 75,
                            'remainingCount': 25,
                            'totalCount': 100,
                            'resetsAt': '2026-10-30T03:00:00Z',
                        },
                        'weekly': {
                            'state': 'metered',
                            'windowSeconds': 604800,
                            'remainingPercent': 80,
                            'usedCount': 20,
                            'remainingCount': 80,
                            'totalCount': 100,
                            'resetsAt': '2026-11-01T00:00:00Z',
                        },
                    },
                ],
                'omittedModelCount': 0,
            },
            'meta': {
                'freshness': 'stale',
                'upstreamState': 'degraded',
                'fetchedAt': '2026-10-30T01:59:00Z',
            },
        },
    }


class QuotaProjectionTests(unittest.TestCase):
    def test_given_local_snapshot_when_projected_then_currency_and_windows_stay_separate(
        self,
    ) -> None:
        projection = normalize_quota_snapshot(
            synthetic_snapshot(),
            enabled_sources=['deepseek_balance', 'minimax_quota'],
            observed_at='2026-10-30T02:01:00Z',
        )

        self.assertEqual(
            [(item['currency'], item['display']) for item in projection['deepseek']['balances']],
            [('CNY', '¥1.25'), ('USD', '$0.00')],
        )
        self.assertEqual(
            [(item['model'], item['window'], item['value'], item['maximum'])
             for item in projection['minimax']['windows']],
            [('Model A', '当前周期', 25, 100), ('Model A', '周周期', 80, 100)],
        )
        self.assertIn('本机各来源独立', projection['identity_scope'])
        self.assertEqual(projection['collector']['state_label'], '本机额度来源已启用')

    def test_given_zero_and_missing_fields_when_projected_then_zero_is_not_unknown(self) -> None:
        payload = synthetic_snapshot()
        payload['minimax']['quota']['models'][0]['interval'].update(
            {'remainingPercent': None, 'remainingCount': None, 'totalCount': None}
        )

        projection = normalize_quota_snapshot(payload, enabled_sources=['minimax_quota'])

        self.assertEqual(projection['deepseek']['balances'][1]['display'], '$0.00')
        self.assertIsNone(projection['minimax']['windows'][0]['value'])
        self.assertIsNone(projection['minimax']['windows'][0]['maximum'])
        self.assertEqual(projection['minimax']['windows'][0]['status_label'], '额度未知')

    def test_given_unlimited_state_and_residual_meter_when_projected_then_state_wins(self) -> None:
        payload = synthetic_snapshot()
        payload['minimax']['quota']['models'][0]['interval'].update(
            {'state': 'unlimited', 'remainingPercent': 80}
        )

        projection = normalize_quota_snapshot(payload, enabled_sources=['minimax_quota'])

        self.assertEqual(projection['minimax']['windows'][0]['status_label'], '不限量')
        self.assertIsNone(projection['minimax']['windows'][0]['value'])
        self.assertIsNone(projection['minimax']['windows'][0]['maximum'])

    def test_given_model_cap_when_projected_then_omitted_models_are_disclosed(self) -> None:
        payload = synthetic_snapshot()
        model = payload['minimax']['quota']['models'][0]
        payload['minimax']['quota']['models'] = [
            {**model, 'key': f'model-{index}', 'name': f'Model {index}'}
            for index in range(10)
        ]
        payload['minimax']['quota']['omittedModelCount'] = 2

        projection = normalize_quota_snapshot(payload, enabled_sources=['minimax_quota'])
        scene = build_quota_scene(projection)
        ids: list[str] = []

        def visit(node: dict[str, object]) -> None:
            ids.append(node['id'])
            for child in node.get('children', []):
                visit(child)

        visit(scene['root'])
        self.assertEqual(len(projection['minimax']['windows']), 16)
        self.assertEqual(projection['minimax']['omitted_model_count'], 2)
        self.assertIn('quota-minimax-omitted-models', ids)

    def test_given_stale_metadata_when_projected_then_freshness_and_source_health_are_distinct(
        self,
    ) -> None:
        projection = normalize_quota_snapshot(
            synthetic_snapshot(),
            enabled_sources=['deepseek_balance', 'minimax_quota'],
        )

        self.assertEqual(projection['minimax']['freshness_label'], '陈旧')
        self.assertEqual(projection['minimax']['upstream_label'], '来源降级')
        self.assertEqual(len(projection['minimax']['windows']), 2)
        self.assertEqual(projection['deepseek']['freshness_label'], '新鲜')

    def test_given_unconfigured_sources_when_projected_then_unknown_is_not_zero(self) -> None:
        projection = normalize_quota_snapshot(
            {
                'deepseek': {'balance': None, 'meta': {'errorCode': 'NOT_CONFIGURED'}},
                'minimax': {'quota': None, 'meta': {'errorCode': 'NOT_ENABLED'}},
            },
            enabled_sources=['deepseek_balance'],
        )

        self.assertEqual(projection['deepseek']['state_label'], '本机密钥未配置')
        self.assertEqual(projection['minimax']['state_label'], '来源未启用')
        self.assertEqual(projection['deepseek']['balances'], [])
        self.assertEqual(projection['minimax']['windows'], [])

    def test_given_unselected_sources_when_rendered_then_dashboard_shows_only_add_cta(self) -> None:
        projection = normalize_quota_snapshot({}, enabled_sources=[])
        scene = build_quota_scene(projection)
        ids: list[str] = []
        text_values: list[str] = []
        actions: list[str] = []

        def visit(node: dict[str, object]) -> None:
            ids.append(node['id'])
            props = node.get('props', {})
            if isinstance(props, dict):
                if isinstance(props.get('text'), str):
                    text_values.append(props['text'])
                if isinstance(props.get('action'), str):
                    actions.append(props['action'])
            for child in node.get('children', []):
                visit(child)

        visit(scene['root'])
        self.assertIn('quota-no-sources-add', ids)
        self.assertNotIn('quota-sources-manage', ids)
        self.assertNotIn('quota-deepseek', ids)
        self.assertNotIn('quota-minimax', ids)
        self.assertNotIn('quota-codex', ids)
        self.assertIn('quota.sources.configure', actions)
        self.assertNotIn('来源未启用', '\n'.join(text_values))
        self.assertNotIn('密钥未配置', '\n'.join(text_values))

    def test_given_selected_vendor_without_key_when_rendered_then_show_configuration_cta(self) -> None:
        projection = normalize_quota_snapshot(
            {'deepseek': {'balance': None, 'meta': {'errorCode': 'NOT_CONFIGURED'}}},
            enabled_sources=['deepseek_balance'],
        )
        scene = build_quota_scene(projection)
        ids: list[str] = []
        actions: list[str] = []

        def visit(node: dict[str, object]) -> None:
            ids.append(node['id'])
            props = node.get('props', {})
            if isinstance(props, dict) and isinstance(props.get('action'), str):
                actions.append(props['action'])
            for child in node.get('children', []):
                visit(child)

        visit(scene['root'])
        self.assertIn('quota-deepseek-configure', ids)
        self.assertNotIn('quota-deepseek-source-state', ids)
        self.assertNotIn('quota-deepseek-updated', ids)
        self.assertIn('quota.source.configure:deepseek_balance', actions)
        self.assertNotIn('quota-minimax', ids)

    def test_given_account_and_management_fields_when_projected_then_private_values_are_removed(
        self,
    ) -> None:
        payload = synthetic_snapshot()
        payload['deepseek']['accountId'] = 'synthetic-private-account'
        payload['minimax']['quota']['accountId'] = 'synthetic-private-account'
        payload['deepseek']['balance']['apiKey'] = 'synthetic-secret'
        payload['managementUrl'] = 'private'

        projection = normalize_quota_snapshot(
            payload,
            enabled_sources=['deepseek_balance', 'minimax_quota'],
        )
        serialized = json.dumps(projection, ensure_ascii=False)

        self.assertNotIn('synthetic-private-account', serialized)
        self.assertNotIn('synthetic-secret', serialized)
        self.assertNotIn('managementUrl', serialized)

    def test_given_scene_when_built_then_freshness_badges_and_quota_visuals_are_present(
        self,
    ) -> None:
        projection = normalize_quota_snapshot(
            synthetic_snapshot(),
            enabled_sources=['deepseek_balance', 'minimax_quota'],
        )
        scene = build_quota_scene(projection)
        kinds: list[str] = []

        def visit(node: dict[str, object]) -> None:
            kinds.append(node['kind'])
            for child in node.get('children', []):
                visit(child)

        visit(scene['root'])
        self.assertEqual(scene['theme']['background'], '#1A1820')
        self.assertEqual(scene['theme']['accent'], '#C4B5FD')
        self.assertFalse(quota_window_spec()['text_selectable'])
        self.assertIn('合成演示', quota_window_spec(demo=True)['title'])
        self.assertEqual(kinds.count('progress'), 2)
        self.assertIn('metric', kinds)
        self.assertGreaterEqual(kinds.count('badge'), 3)
        self.assertIn('collector', scene['data'])
        self.assertNotIn('api', scene['data'])

    def test_given_demo_fixture_when_projected_then_all_values_are_synthetic(self) -> None:
        projection = normalize_quota_snapshot(
            synthetic_demo_snapshot(),
            observed_at='2026-10-31T00:00:00Z',
            demo=True,
        )

        self.assertEqual(projection['collector']['state_label'], '合成演示数据')
        self.assertEqual(projection['deepseek']['state_label'], '余额快照')
        self.assertEqual(projection['minimax']['state_label'], '模型周期额度')


if __name__ == '__main__':
    unittest.main()
