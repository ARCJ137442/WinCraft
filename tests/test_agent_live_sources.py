import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = ROOT / 'examples' / 'integrations' / 'agent-board'
sys.path.insert(0, str(EXAMPLE_DIR))

from activity_board import ACTIVITY_VALIDATOR, aggregate_activities  # noqa: E402
from global_overview import (  # noqa: E402
    GlobalOverviewState,
    build_global_overview_scene,
    reconcile_view_state,
)
from live_sources import (  # noqa: E402
    LIVE_SOURCE_LABELS,
    SourceReadError,
    load_live_snapshot,
    merge_codex_app_snapshot,
    normalize_codex_app_snapshot,
    normalize_claude_agents,
    normalize_codex_threads,
    summarize_live_snapshot,
)

NOW = datetime(2026, 10, 29, 8, 0, tzinfo=timezone.utc)


def walk_nodes(node):
    yield node
    for child in node.get('children', []):
        yield from walk_nodes(child)


class LiveSourceNormalizationTests(unittest.TestCase):
    def test_codex_app_snapshot_keeps_requested_fields_and_redacts_preview(self):
        thread_id = '00000000-0000-4000-8000-000000000001'
        payload = {
            'snapshot_version': 1,
            'source_health': 'online',
            'captured_at': '2026-10-29T08:00:00Z',
            'threads': [
                {
                    'thread_id': thread_id,
                    'title': 'Synthetic Codex App thread',
                    'status': 'active',
                    'project_label': 'Synthetic project',
                    'last_agent_output': '继续推进。' + 'token=' + 'synthetic-secret-value C:\\Synthetic\\private\\file.txt',
                    'last_output_kind': 'agent_message',
                    'source_sequence': 0,
                }
            ],
        }

        records, health = normalize_codex_app_snapshot(
            payload,
            observed_at=NOW,
            sequence=3,
        )

        self.assertEqual(health, 'online')
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record['source_type'], 'codex-app')
        self.assertEqual(record['normalized_status'], 'running')
        self.assertEqual(record['display_name'], 'Synthetic Codex App thread')
        self.assertEqual(record['project_label'], 'Synthetic project')
        self.assertEqual(record['codex_app_thread_id'], thread_id)
        self.assertEqual(record['last_output_kind'], 'agent_message')
        self.assertIn('[凭据已隐藏]', record['summary'])
        self.assertIn('[本机路径]', record['summary'])
        ACTIVITY_VALIDATOR.validate(record)

    def test_codex_app_preview_shows_title_status_project_and_latest_agent_output(self):
        records, _ = normalize_codex_app_snapshot(
            {
                'snapshot_version': 1,
                'source_health': 'online',
                'threads': [
                    {
                        'thread_id': '00000000-0000-4000-8000-000000000001',
                        'title': 'Synthetic Codex App thread',
                        'status': 'active',
                        'project_label': 'Synthetic project',
                        'last_agent_output': '最近 Agent 输出片段',
                        'last_output_kind': 'agent_message',
                        'source_sequence': 0,
                    }
                ],
            },
            observed_at=NOW,
            sequence=1,
        )
        projection = aggregate_activities(records, now=NOW)
        projection.update(
            {
                'source_health': {
                    'codex': 'online',
                    'codex-app': 'online',
                    'claude-code': 'online',
                },
                'source_labels': LIVE_SOURCE_LABELS,
                'data_mode_label': 'Codex App + CLI 实时只读',
                'codex_app_links_enabled': True,
                'source_age_seconds': {'codex': 2, 'codex-app': 1, 'claude-code': 3},
                'source_freshness': {
                    'codex': 'fresh',
                    'codex-app': 'fresh',
                    'claude-code': 'fresh',
                },
            }
        )

        scene, _, _ = build_global_overview_scene(projection, GlobalOverviewState())
        preview = scene['data']['codex_app_preview'][0]
        self.assertEqual(preview['project'], '项目：Synthetic project')
        self.assertEqual(preview['output'], '最近 Agent 输出：最近 Agent 输出片段')
        self.assertTrue(preview['status'])

        nodes = list(walk_nodes(scene['root']))
        title = next(node for node in nodes if node['id'] == 'global-codex-app-preview-name-0-0')
        self.assertEqual(title['props']['label'], 'Synthetic Codex App thread')
        self.assertEqual(title['props']['native_window_action']['operation'], 'open_thread')

        source_scene, _, _ = build_global_overview_scene(
            projection,
            GlobalOverviewState(source='codex-app'),
        )
        source_row = source_scene['data']['sessions'][0]
        self.assertEqual(source_row['name'], 'Synthetic Codex App thread')
        self.assertTrue(source_row['status'])
        self.assertEqual(source_row['project'], '项目：Synthetic project')
        self.assertEqual(source_row['output'], '最近 Agent 输出：最近 Agent 输出片段')

    def test_source_freshness_tracks_last_success_and_disconnect_age(self):
        with (
            patch('live_sources.read_codex_threads', return_value=([], 'online')),
            patch('live_sources.read_claude_agents', return_value=([], 'online')),
        ):
            first = load_live_snapshot(sequence=1, now=NOW)

        with (
            patch(
                'live_sources.read_codex_threads',
                side_effect=SourceReadError('codex', 'timeout'),
            ),
            patch(
                'live_sources.read_claude_agents',
                side_effect=SourceReadError('claude-code', 'timeout'),
            ),
        ):
            later = load_live_snapshot(
                first,
                sequence=2,
                now=NOW + timedelta(seconds=35),
            )

        self.assertEqual(later.projection['source_age_seconds']['codex'], 35)
        self.assertEqual(later.projection['source_age_seconds']['claude-code'], 35)
        self.assertEqual(later.projection['source_freshness']['codex'], 'disconnected')
        self.assertEqual(later.projection['source_freshness']['claude-code'], 'disconnected')
        self.assertIsNone(later.projection['source_age_seconds']['codex-app'])

    def test_codex_app_snapshot_rejects_arbitrary_fields_and_bad_thread_ids(self):
        base = {
            'snapshot_version': 1,
            'source_health': 'online',
            'threads': [
                {
                    'thread_id': 'not-a-uuid',
                    'title': 'thread',
                    'status': 'active',
                    'project_label': 'Synthetic project',
                    'last_agent_output': '',
                    'last_output_kind': 'unavailable',
                }
            ],
        }
        with self.assertRaises(SourceReadError):
            normalize_codex_app_snapshot({**base, 'arbitrary_url': 'https://example.invalid'}, observed_at=NOW, sequence=1)
        records, health = normalize_codex_app_snapshot(base, observed_at=NOW, sequence=1)
        self.assertEqual(records, [])
        self.assertEqual(health, 'partial')

    def test_codex_app_snapshot_preserves_connector_order(self):
        records, health = normalize_codex_app_snapshot(
            {
                'snapshot_version': 1,
                'source_health': 'online',
                'threads': [
                    {
                        'thread_id': '00000000-0000-4000-8000-000000000002',
                        'title': 'Second in connector order',
                        'status': 'idle',
                        'project_label': 'Project',
                        'last_agent_output': 'Second',
                        'last_output_kind': 'connector_summary',
                        'source_sequence': 1,
                    },
                    {
                        'thread_id': '00000000-0000-4000-8000-000000000001',
                        'title': 'First in connector order',
                        'status': 'active',
                        'project_label': 'Project',
                        'last_agent_output': 'First',
                        'last_output_kind': 'agent_message',
                        'source_sequence': 0,
                    },
                ],
            },
            observed_at=NOW,
            sequence=1,
        )
        from activity_board import aggregate_activities

        projection = aggregate_activities(records, now=NOW)
        self.assertEqual(health, 'online')
        self.assertEqual(
            [session['display_name'] for session in projection['sessions']],
            ['First in connector order', 'Second in connector order'],
        )

    def test_claude_source_status_is_mapped_without_names_or_paths(self):
        payload = [
            {
                'id': 'private-session-id-a',
                'sessionId': 'private-conversation-id-a',
                'state': 'blocked',
                'name': 'private project title',
                'cwd': 'C:/private/worktree',
            },
            {
                'id': 'private-session-id-b',
                'sessionId': 'private-conversation-id-b',
                'state': 'idle',
                'name': 'another private title',
                'cwd': 'C:/private/other',
            },
            {
                'id': 'private-session-id-c',
                'state': 'future-state',
                'name': 'not surfaced',
                'cwd': 'C:/not surfaced',
            },
        ]

        records, health = normalize_claude_agents(
            payload,
            observed_at=NOW,
            sequence=4,
        )

        self.assertEqual(health, 'partial')
        self.assertEqual(len(records), 3)
        self.assertEqual(
            [record['normalized_status'] for record in records],
            ['blocked', 'idle', 'unknown'],
        )
        self.assertEqual(
            [record['source_status'] for record in records],
            ['blocked', 'idle', 'unknown'],
        )
        serialized = json.dumps(records)
        for private_value in (
            'private-session-id',
            'private-conversation-id',
            'private project title',
            'C:/private',
        ):
            self.assertNotIn(private_value, serialized)
        self.assertTrue(all(record['session_id'].startswith('sha256-') for record in records))
        self.assertTrue(all(record['summary'] == '' for record in records))
        self.assertTrue(all(record['provenance'] == 'official-cli' for record in records))
        for record in records:
            ACTIVITY_VALIDATOR.validate(record)

    def test_claude_missing_identity_is_skipped_and_marks_source_partial(self):
        records, health = normalize_claude_agents(
            [{'state': 'blocked', 'cwd': 'C:/private'}],
            observed_at=NOW,
            sequence=1,
        )

        self.assertEqual(records, [])
        self.assertEqual(health, 'partial')

    def test_claude_duplicate_identity_fails_closed(self):
        payload = [
            {'id': 'same-id', 'state': 'blocked'},
            {'id': 'same-id', 'state': 'idle'},
        ]
        with self.assertRaises(SourceReadError) as error:
            normalize_claude_agents(payload, observed_at=NOW, sequence=1)
        self.assertEqual(error.exception.reason_code, 'duplicate_session_identity')

    def test_codex_active_flags_and_known_states_are_mapped(self):
        payload = {
            'data': [
                {
                    'id': 'private-thread-waiting-input',
                    'status': {'type': 'active', 'activeFlags': ['waitingOnUserInput']},
                    'preview': 'private prompt text',
                    'name': 'private title',
                    'cwd': 'C:/private/worktree',
                    'path': 'C:/private/rollout.jsonl',
                },
                {
                    'id': 'private-thread-waiting-approval',
                    'status': {'type': 'active', 'activeFlags': ['waitingOnApproval']},
                },
                {'id': 'private-thread-running', 'status': {'type': 'active', 'activeFlags': []}},
                {'id': 'private-thread-idle', 'status': {'type': 'idle'}},
                {'id': 'private-thread-error', 'status': {'type': 'systemError'}},
                {'id': 'private-thread-unloaded', 'status': {'type': 'notLoaded'}},
                {'id': 'private-thread-future', 'status': {'type': 'futureStatus'}},
            ],
            'nextCursor': None,
        }

        records, health = normalize_codex_threads(payload, observed_at=NOW, sequence=5)

        self.assertEqual(health, 'partial')
        self.assertEqual(
            [record['normalized_status'] for record in records],
            [
                'waiting_input',
                'waiting_approval',
                'running',
                'idle',
                'failed',
                'unknown',
                'unknown',
            ],
        )
        serialized = json.dumps(records)
        for private_value in (
            'private-thread-',
            'private prompt text',
            'private title',
            'C:/private',
            'rollout.jsonl',
        ):
            self.assertNotIn(private_value, serialized)
        self.assertTrue(all(record['session_id'].startswith('sha256-') for record in records))
        self.assertTrue(all(record['summary'] == '' for record in records))
        for record in records:
            ACTIVITY_VALIDATOR.validate(record)

    def test_codex_parent_identity_is_opaque_and_requires_present_parent(self):
        records, health = normalize_codex_threads(
            {
                'data': [
                    {'id': 'parent-id', 'status': {'type': 'idle'}},
                    {'id': 'child-id', 'parentThreadId': 'parent-id', 'status': {'type': 'active'}},
                    {'id': 'orphan-id', 'parentThreadId': 'missing-parent', 'status': {'type': 'idle'}},
                ]
            },
            observed_at=NOW,
            sequence=2,
        )

        self.assertEqual(health, 'online')
        self.assertEqual(records[1]['parent_session_id'], records[0]['session_id'])
        self.assertIsNone(records[2]['parent_session_id'])
        self.assertNotIn('parent-id', json.dumps(records))


class LiveSourceFailureTests(unittest.TestCase):
    def test_codex_app_snapshot_merges_into_the_same_read_only_projection(self):
        codex_records, _ = normalize_codex_threads(
            {'data': [{'id': 'codex-cli-id', 'status': {'type': 'active', 'activeFlags': []}}]},
            observed_at=NOW,
            sequence=1,
        )
        claude_records, _ = normalize_claude_agents(
            [{'id': 'claude-id', 'state': 'idle'}],
            observed_at=NOW,
            sequence=1,
        )
        with (
            patch('live_sources.read_codex_threads', return_value=(codex_records, 'online')),
            patch('live_sources.read_claude_agents', return_value=(claude_records, 'online')),
        ):
            base = load_live_snapshot(sequence=1, now=NOW)
        app_payload = {
            'snapshot_version': 1,
            'source_health': 'online',
            'threads': [
                {
                    'thread_id': '00000000-0000-4000-8000-000000000002',
                    'title': 'Synthetic Codex App thread',
                    'status': 'active',
                    'project_label': 'Synthetic project',
                    'last_agent_output': 'Local CLI state DB had zero threads.',
                    'last_output_kind': 'agent_message',
                    'source_sequence': 0,
                }
            ],
        }

        merged = merge_codex_app_snapshot(
            base,
            app_payload,
            sequence=2,
            now=NOW,
            links_enabled=True,
        )

        self.assertEqual(merged.projection['source_health'], {
            'codex': 'online',
            'codex-app': 'online',
            'claude-code': 'online',
        })
        self.assertTrue(merged.projection['codex_app_links_enabled'])
        self.assertEqual(len(merged.projection['sessions']), 3)
        self.assertEqual(
            {x['source_type_label'] for x in merged.projection['sessions']},
            {'Codex', 'Claude Code', 'Codex App'},
        )

    def test_codex_app_unavailable_and_disconnected_modes_are_not_claimed_as_live(self):
        with (
            patch('live_sources.read_codex_threads', return_value=([], 'online')),
            patch('live_sources.read_claude_agents', return_value=([], 'online')),
        ):
            base = load_live_snapshot(sequence=1, now=NOW)

        unavailable = merge_codex_app_snapshot(
            base,
            {'source_health': 'disconnected', 'threads': []},
            sequence=2,
            now=NOW,
            links_enabled=True,
        )
        self.assertEqual(unavailable.projection['source_health']['codex-app'], 'unavailable')
        self.assertIn('Codex App 等待 Agent 接入', unavailable.projection['data_mode_label'])

        active_payload = {
            'snapshot_version': 1,
            'source_health': 'online',
            'threads': [
                {
                    'thread_id': '00000000-0000-4000-8000-000000000002',
                    'title': 'Synthetic Codex App thread',
                    'status': 'active',
                    'project_label': 'Synthetic project',
                    'last_agent_output': 'Synthetic output',
                    'last_output_kind': 'agent_message',
                    'source_sequence': 0,
                }
            ],
        }
        online = merge_codex_app_snapshot(
            base,
            active_payload,
            sequence=3,
            now=NOW,
            links_enabled=True,
        )
        disconnected = merge_codex_app_snapshot(
            online,
            {'source_health': 'disconnected', 'threads': []},
            sequence=4,
            now=NOW + timedelta(seconds=1),
            links_enabled=True,
        )
        self.assertEqual(disconnected.projection['source_health']['codex-app'], 'disconnected')
        self.assertIn('Codex App 桥接断开', disconnected.projection['data_mode_label'])

    def test_refresh_drops_detail_for_a_session_that_disappeared(self):
        state = GlobalOverviewState(
            source='claude-code',
            selected_identity=('device', 'provider', 'instance', 'old-session'),
            page=2,
            revision=7,
        )

        next_state = reconcile_view_state({'sessions': []}, state)

        self.assertEqual(next_state.source, 'claude-code')
        self.assertIsNone(next_state.selected_identity)
        self.assertEqual(next_state.page, 0)
        self.assertEqual(next_state.revision, 8)

    def test_failure_marks_only_that_sources_last_snapshot_stale(self):
        codex_records, _ = normalize_codex_threads(
            {'data': [{'id': 'codex-id', 'status': {'type': 'active', 'activeFlags': []}}]},
            observed_at=NOW,
            sequence=1,
        )
        claude_records, _ = normalize_claude_agents(
            [{'id': 'claude-id', 'state': 'blocked'}],
            observed_at=NOW,
            sequence=1,
        )
        with (
            patch('live_sources.read_codex_threads', return_value=(codex_records, 'online')),
            patch('live_sources.read_claude_agents', return_value=(claude_records, 'online')),
        ):
            first = load_live_snapshot(sequence=1, now=NOW)

        with (
            patch('live_sources.read_codex_threads', return_value=(codex_records, 'online')),
            patch(
                'live_sources.read_claude_agents',
                side_effect=SourceReadError('claude-code', 'timeout'),
            ),
        ):
            second = load_live_snapshot(first, sequence=2, now=NOW)

        self.assertEqual(second.projection['source_health'], {
            'codex': 'online',
            'codex-app': 'unavailable',
            'claude-code': 'disconnected',
        })
        by_source = {record['source_type_label']: record for record in second.projection['sessions']}
        self.assertEqual(by_source['Codex']['freshness'], 'fresh')
        self.assertEqual(by_source['Codex']['normalized_status'], 'running')
        self.assertEqual(by_source['Claude Code']['freshness'], 'disconnected')
        self.assertEqual(by_source['Claude Code']['normalized_status'], 'stale')

    def test_initial_source_failure_is_visible_without_fabricating_a_session(self):
        with (
            patch('live_sources.read_codex_threads', return_value=([], 'online')),
            patch(
                'live_sources.read_claude_agents',
                side_effect=SourceReadError('claude-code', 'cli_failed'),
            ),
        ):
            snapshot = load_live_snapshot(sequence=1, now=NOW)

        self.assertEqual(snapshot.projection['source_health']['claude-code'], 'disconnected')
        self.assertEqual(snapshot.projection['source_health']['codex'], 'online')
        self.assertEqual(snapshot.projection['sessions'], [])

    def test_snapshot_log_summary_contains_only_aggregate_statuses(self):
        records, _ = normalize_claude_agents(
            [{'id': 'private-id', 'state': 'blocked', 'name': 'private title'}],
            observed_at=NOW,
            sequence=1,
        )
        with (
            patch('live_sources.read_codex_threads', return_value=([], 'online')),
            patch('live_sources.read_claude_agents', return_value=(records, 'online')),
        ):
            snapshot = load_live_snapshot(sequence=1, now=NOW)

        summary = summarize_live_snapshot(snapshot)
        serialized = json.dumps(summary)
        self.assertEqual(
            summary['status_counts']['claude-code'],
            {'blocked': 1},
        )
        self.assertNotIn('private-id', serialized)
        self.assertNotIn('private title', serialized)
        self.assertNotIn('session_id', serialized)

    def test_live_scene_discloses_scope_and_partial_source_health_without_raw_metadata(self):
        records, health = normalize_claude_agents(
            [{'id': 'private-id', 'state': 'blocked', 'name': 'private title'}],
            observed_at=NOW,
            sequence=1,
        )
        from activity_board import aggregate_activities

        projection = aggregate_activities(records, now=NOW)
        projection.update({
            'source_health': {
                'codex': 'online',
                'codex-app': 'unavailable',
                'claude-code': 'partial',
            },
            'source_labels': {
                'codex': 'Codex CLI · 本机状态库',
                'codex-app': 'Codex App',
                'claude-code': 'Claude Code',
            },
            'data_mode_label': '本机实时只读',
            'codex_app_links_enabled': True,
            'source_age_seconds': {'codex': 5, 'codex-app': None, 'claude-code': 31},
            'source_freshness': {
                'codex': 'fresh',
                'codex-app': 'unavailable',
                'claude-code': 'stale',
            },
        })
        scene, _, _ = build_global_overview_scene(projection, GlobalOverviewState())
        self.assertEqual(scene['data']['summary']['codex_cli_health'], 'CLI 可查询')
        self.assertEqual(scene['data']['summary']['codex_app_health'], '等待 Agent 桥接')
        serialized = json.dumps(scene, ensure_ascii=False)
        self.assertIn('本机实时只读', serialized)
        self.assertIn('Codex CLI · 本机状态库', serialized)
        self.assertIn('Codex App', serialized)
        self.assertIn('CLI 可查询', serialized)
        self.assertIn('等待 Agent 桥接', serialized)
        self.assertIn('CLI 部分可用', serialized)
        self.assertIn('已过期 · 上次成功 31 秒前', serialized)
        self.assertIn('更新于 5 秒前', serialized)
        self.assertIn('尚未收到快照', serialized)
        self.assertIn('已过期 · 上次成功 31 秒前', serialized)
        self.assertIn('阻塞', serialized)
        self.assertNotIn('private-id', serialized)
        self.assertNotIn('private title', serialized)
        self.assertNotIn('source_status', serialized)

    def test_codex_app_title_is_clickable_only_with_host_thread_navigation_capability(self):
        thread_id = '00000000-0000-4000-8000-000000000003'
        records, _ = normalize_codex_app_snapshot(
            {
                'snapshot_version': 1,
                'source_health': 'online',
                'threads': [
                    {
                        'thread_id': thread_id,
                        'title': 'Synthetic Codex App thread',
                        'status': 'active',
                        'project_label': 'Synthetic project',
                        'last_agent_output': 'Synthetic output',
                        'last_output_kind': 'agent_message',
                    }
                ],
            },
            observed_at=NOW,
            sequence=1,
        )
        from activity_board import aggregate_activities

        projection = aggregate_activities(records, now=NOW)
        projection.update({
            'source_health': {'codex': 'online', 'codex-app': 'online', 'claude-code': 'online'},
            'source_labels': {'codex': 'Codex CLI', 'codex-app': 'Codex App', 'claude-code': 'Claude Code'},
            'data_mode_label': 'Codex App + CLI 实时只读',
            'codex_app_links_enabled': True,
        })
        scene, detail_targets, _ = build_global_overview_scene(projection, GlobalOverviewState())
        node = next(node for node in walk_nodes(scene['root']) if node['id']=='global-codex-app-preview-name-0-0')
        self.assertEqual(node['kind'], 'button')
        self.assertEqual(node['props']['appearance'], 'link')
        self.assertEqual(node['props']['native_window_action'], {
            'application': 'codex_app',
            'operation': 'open_thread',
            'thread_id': thread_id,
        })
        self.assertIn('global-codex-app-preview-0-0', detail_targets)
        self.assertIn('Synthetic Codex App thread', json.dumps(scene, ensure_ascii=False))
        self.assertIn('Synthetic output', json.dumps(scene, ensure_ascii=False))
        self.assertIn('最近 Agent 输出', json.dumps(scene, ensure_ascii=False))
        self.assertNotIn(thread_id, json.dumps(scene['data']))
        self.assertNotIn('codex://', json.dumps(scene))

        projection['codex_app_links_enabled'] = False
        disabled_scene, _, _ = build_global_overview_scene(projection, GlobalOverviewState())
        disabled_node = next(node for node in walk_nodes(disabled_scene['root']) if node['id']=='global-codex-app-preview-name-0-0')
        self.assertEqual(disabled_node['kind'], 'text')
        self.assertNotIn(thread_id, json.dumps(disabled_scene))


if __name__ == '__main__':
    unittest.main()
