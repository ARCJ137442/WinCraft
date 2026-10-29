import json
import sqlite3
import sys
import tempfile
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
    LiveSnapshot,
    SourceReadError,
    load_live_snapshot,
    merge_codex_app_snapshot,
    normalize_codex_app_snapshot,
    normalize_claude_agents,
    normalize_codex_threads,
    summarize_live_snapshot,
    _codex_last_agent_output,
    _read_claude_latest_outputs,
    _read_claude_last_agent_output,
    _read_codex_rollout_agent_output,
    _read_codex_latest_outputs,
    read_codex_app_local_threads,
)

NOW = datetime(2026, 10, 29, 8, 0, tzinfo=timezone.utc)


def walk_nodes(node):
    yield node
    for child in node.get('children', []):
        yield from walk_nodes(child)


def create_codex_app_state_fixture(root, rows):
    root.mkdir(parents=True, exist_ok=True)
    database = root / 'state_fixture.sqlite'
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            'CREATE TABLE threads ('
            'id TEXT, title TEXT, name TEXT, cwd TEXT, model TEXT, source TEXT, '
            'tokens_used INTEGER, updated_at_ms INTEGER, originator TEXT, '
            'rollout_path TEXT, archived INTEGER)'
        )
        for row in rows:
            rollout_path = None
            if row.get('agent_output') is not None:
                rollout_path = root / 'sessions' / '2026' / '10' / '29' / f"rollout-{row['id']}.jsonl"
                rollout_path.parent.mkdir(parents=True, exist_ok=True)
                entries = [
                    {'type': 'session_meta', 'payload': {'id': row['id']}},
                    {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'synthetic private prompt'}},
                    {'type': 'event_msg', 'payload': {'type': 'agent_message', 'message': row['agent_output']}},
                    {'type': 'event_msg', 'payload': {'type': 'tool_output', 'message': 'synthetic tool output'}},
                ]
                rollout_path.write_text(
                    ''.join(json.dumps(entry) + '\n' for entry in entries),
                    encoding='utf-8',
                )
            connection.execute(
                'INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    row['id'],
                    row.get('title', ''),
                    row.get('name'),
                    row.get('cwd', ''),
                    row.get('model'),
                    row.get('source', 'vscode'),
                    row.get('tokens_used', 0),
                    row.get('updated_at_ms', 0),
                    row.get('originator', 'Codex Desktop'),
                    str(rollout_path) if rollout_path else None,
                    row.get('archived', 0),
                ),
            )
        connection.commit()
    finally:
        connection.close()
    return database


class LiveSourceNormalizationTests(unittest.TestCase):
    def setUp(self):
        local_state = patch(
            'live_sources.read_codex_app_local_threads',
            return_value=([], 'unavailable'),
        )
        local_state.start()
        self.addCleanup(local_state.stop)

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
        source_nodes = list(walk_nodes(source_scene['root']))
        freshness = next(node for node in source_nodes if node['id'] == 'global-source-freshness')
        self.assertEqual(freshness['props']['text'], '数据新鲜度：刚刚更新（1 秒前）')
        title = next(node for node in source_nodes if node['id'].startswith('global-session-name-'))
        self.assertEqual(title['props']['label'], 'Synthetic Codex App thread')
        status = next(node for node in source_nodes if node['id'].startswith('global-session-status-'))
        self.assertEqual(status['props']['text'], {'$path': '/sessions/0/status'})
        project = next(node for node in source_nodes if node['id'].startswith('global-session-project-'))
        self.assertEqual(project['props']['text'], {'$path': '/sessions/0/project'})
        output = next(node for node in source_nodes if node['id'].startswith('global-session-output-'))
        self.assertEqual(output['props']['text'], {'$path': '/sessions/0/output'})
        self.assertNotIn('size', output['props'])

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

    def test_codex_desktop_local_state_adds_safe_metadata_and_agent_output(self):
        desktop_id = '00000000-0000-4000-8000-000000000101'
        cli_id = '00000000-0000-4000-8000-000000000102'
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / '.codex'
            create_codex_app_state_fixture(
                root,
                [
                    {
                        'id': desktop_id,
                        'title': 'Synthetic Desktop title',
                        'name': 'Synthetic Desktop session',
                        'cwd': 'C:/Private/SyntheticProject',
                        'originator': 'Codex Desktop',
                        'updated_at_ms': 200,
                        'agent_output': 'Synthetic Agent reply token=synthetic-secret C:\\Private\\note.md',
                    },
                    {
                        'id': cli_id,
                        'title': 'Synthetic CLI session',
                        'cwd': 'C:/Private/OtherProject',
                        'originator': 'Codex CLI',
                        'updated_at_ms': 100,
                    },
                    {
                        'id': '00000000-0000-4000-8000-000000000104',
                        'title': 'Synthetic Desktop without output',
                        'cwd': 'C:/Private/SecondProject',
                        'originator': 'Codex Desktop',
                        'updated_at_ms': 150,
                    },
                    {
                        'id': '00000000-0000-4000-8000-000000000103',
                        'title': 'Archived Desktop session',
                        'cwd': 'C:/Private/ArchivedProject',
                        'originator': 'Codex Desktop',
                        'archived': 1,
                        'updated_at_ms': 50,
                    },
                ],
            )
            records, health = read_codex_app_local_threads(
                observed_at=NOW,
                sequence=6,
                codex_root=root,
            )

        self.assertEqual(health, 'local_state')
        self.assertEqual(len(records), 2)
        record = next(item for item in records if item['codex_app_thread_id'] == desktop_id)
        self.assertEqual(record['source_type'], 'codex-app')
        self.assertEqual(record['provider_id'], 'codex-app-local-state')
        self.assertEqual(record['display_name'], 'Synthetic Desktop session')
        self.assertEqual(record['project_label'], 'SyntheticProject')
        self.assertEqual(record['normalized_status'], 'unknown')
        self.assertEqual(record['last_output_kind'], 'agent_message')
        self.assertEqual(
            record['summary'],
            'Synthetic Agent reply [凭据已隐藏] [本机路径]',
        )
        ACTIVITY_VALIDATOR.validate(record)
        with (
            patch('live_sources.read_codex_app_local_threads', return_value=(records, 'local_state')),
            patch('live_sources.read_codex_threads', return_value=([], 'online')),
            patch('live_sources.read_claude_agents', return_value=([], 'online')),
        ):
            live_snapshot = load_live_snapshot(sequence=7, now=NOW)
        self.assertEqual(live_snapshot.projection['source_health']['codex-app'], 'local_state')
        self.assertEqual(
            live_snapshot.projection['data_mode_label'],
            '本机 Codex Desktop 状态库只读 · Agent 状态待桥接',
        )
        self.assertEqual(len(live_snapshot.records_by_source['codex-app']), 2)

        projection = aggregate_activities(records, now=NOW)
        projection.update(
            {
                'source_health': {'codex': 'online', 'codex-app': 'local_state', 'claude-code': 'online'},
                'source_labels': LIVE_SOURCE_LABELS,
                'data_mode_label': '本机 Codex Desktop 状态库只读',
            }
        )
        scene, _, _ = build_global_overview_scene(projection, GlobalOverviewState())
        preview = scene['data']['codex_app_preview'][0]
        self.assertEqual(preview['project'], '项目：SyntheticProject')
        self.assertEqual(
            preview['output'],
            '最近 Agent 输出：Synthetic Agent reply [凭据已隐藏] [本机路径]',
        )
        self.assertEqual(scene['data']['summary']['codex_app_health'], '本机状态库可读')
        self.assertEqual(scene['data']['summary']['codex_parallel'], '—')
        app_scene, _, _ = build_global_overview_scene(
            projection,
            GlobalOverviewState(source='codex-app'),
        )
        source_summary = next(
            node['props']['text']
            for node in walk_nodes(app_scene['root'])
            if node['id'] == 'global-source-summary'
        )
        self.assertIn('status unknown', source_summary)
        serialized = json.dumps(scene, ensure_ascii=False)
        for forbidden in (desktop_id, cli_id, 'C:/Private/', 'synthetic-secret', 'Private note'):
            self.assertNotIn(forbidden, serialized)

        previous = LiveSnapshot(
            projection,
            {'codex-app': records, 'codex': [], 'claude-code': []},
            6,
            {'codex-app': NOW},
        )
        merged = merge_codex_app_snapshot(
            previous,
            {
                'snapshot_version': 1,
                'source_health': 'online',
                'captured_at': '2026-10-29T08:00:00Z',
                'threads': [
                    {
                        'thread_id': desktop_id,
                        'title': 'Connector title',
                        'status': 'active',
                        'project_label': 'Connector project',
                        'last_agent_output': 'Connector Agent output',
                        'last_output_kind': 'agent_message',
                    }
                ],
            },
            sequence=7,
            now=NOW,
            links_enabled=True,
        )
        merged_records = merged.records_by_source['codex-app']
        self.assertEqual(len(merged_records), 2)
        connector_record = next(item for item in merged_records if item['codex_app_thread_id'] == desktop_id)
        local_only_record = next(item for item in merged_records if item['codex_app_thread_id'] != desktop_id)
        self.assertEqual(connector_record['provider_id'], 'codex-app-connector')
        self.assertEqual(connector_record['display_name'], 'Connector title')
        self.assertEqual(connector_record['normalized_status'], 'running')
        self.assertEqual(connector_record['summary'], 'Connector Agent output')
        self.assertEqual(local_only_record['provider_id'], 'codex-app-local-state')
        self.assertEqual(merged.projection['source_health']['codex-app'], 'partial')

    def test_codex_desktop_local_rollout_path_fails_closed_without_session_meta_match(self):
        thread_id = '00000000-0000-4000-8000-000000000111'
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / '.codex'
            rollout = root / 'sessions' / '2026' / '10' / '29' / f'rollout-{thread_id}.jsonl'
            rollout.parent.mkdir(parents=True)
            rollout.write_text(
                json.dumps({'type': 'session_meta', 'payload': {'id': '00000000-0000-4000-8000-000000000999'}}) + '\n'
                + json.dumps({'type': 'event_msg', 'payload': {'type': 'agent_message', 'message': 'Must not be displayed'}}) + '\n',
                encoding='utf-8',
            )

            output = _read_codex_rollout_agent_output(rollout, thread_id)

        self.assertEqual(output, '')

    def test_claude_source_shows_safe_name_and_project_without_paths_or_ids(self):
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
        self.assertEqual(
            [record['display_name'] for record in records],
            ['private project title', 'another private title', 'not surfaced'],
        )
        self.assertEqual(
            [record['project_label'] for record in records],
            ['worktree', 'other', ''],
        )
        serialized = json.dumps(records)
        for private_value in (
            'private-session-id',
            'private-conversation-id',
            'C:/private',
        ):
            self.assertNotIn(private_value, serialized)
        self.assertIn('private project title', serialized)
        self.assertTrue(all(record['session_id'].startswith('sha256-') for record in records))
        self.assertTrue(all(record['summary'] == '' for record in records))
        self.assertTrue(all(record['last_output_kind'] == 'unavailable' for record in records))
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

    def test_codex_active_flags_map_status_and_thread_preview_is_not_agent_output(self):
        payload = {
            'data': [
                {
                    'id': 'private-thread-waiting-input',
                    'status': {'type': 'active', 'activeFlags': ['waitingOnUserInput']},
                    'preview': 'Synthetic latest activity token=synthetic-secret C:\\private\\note.txt',
                    'name': 'Synthetic Codex CLI session',
                    'cwd': 'C:/Users/SyntheticUser/Develop/WinCraft',
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
            'C:/Users/SyntheticUser/Develop/WinCraft',
            'rollout.jsonl',
            'synthetic-secret',
            'Synthetic latest activity',
        ):
            self.assertNotIn(private_value, serialized)
        self.assertEqual(records[0]['display_name'], 'Synthetic Codex CLI session')
        self.assertEqual(records[0]['project_label'], 'WinCraft')
        self.assertEqual(records[0]['summary'], '')
        self.assertTrue(all(record['last_output_kind'] == 'unavailable' for record in records))
        self.assertTrue(all(record['session_id'].startswith('sha256-') for record in records))
        for record in records:
            ACTIVITY_VALIDATOR.validate(record)

    def test_codex_thread_read_extracts_only_the_last_agent_message(self):
        response = {
            'thread': {
                'turns': [
                    {
                        'items': [
                            {'type': 'userMessage', 'content': [{'type': 'text', 'text': 'user text'}]},
                            {'type': 'agentMessage', 'text': 'interim commentary', 'phase': 'commentary'},
                        ]
                    },
                    {
                        'items': [
                            {
                                'type': 'agentMessage',
                                'text': 'last response token=synthetic-secret C:\\Synthetic\\note.md',
                                'phase': 'final_answer',
                            },
                            {'type': 'commandExecution', 'aggregatedOutput': 'tool output must not be shown'},
                            {'type': 'agentMessage', 'text': 'latest progress token=synthetic-secret', 'phase': 'commentary'},
                        ]
                    },
                ]
            }
        }

        self.assertEqual(
            _codex_last_agent_output(response),
            'latest progress [凭据已隐藏]',
        )

        records, _ = normalize_codex_threads(
            {
                'data': [
                    {
                        'id': 'synthetic-thread-id',
                        'name': 'Synthetic Codex CLI session',
                        'preview': 'first user prompt',
                        'status': {'type': 'active', 'activeFlags': []},
                    }
                ]
            },
            observed_at=NOW,
            sequence=1,
            agent_outputs={'synthetic-thread-id': _codex_last_agent_output(response)},
        )
        self.assertEqual(records[0]['summary'], 'latest progress [凭据已隐藏]')
        self.assertEqual(records[0]['last_output_kind'], 'agent_message')

    def test_codex_latest_output_reads_are_bounded_and_cached_in_memory(self):
        class FakeClient:
            def __init__(self):
                self.calls = []

            def request(self, method, params, *, timeout_seconds=None):
                self.calls.append((method, params['threadId'], timeout_seconds))
                return {
                    'thread': {
                        'turns': [
                            {'items': [{'type': 'agentMessage', 'text': 'Synthetic response', 'phase': 'final_answer'}]}
                        ]
                    }
                }

        client = FakeClient()
        threads = [
            {'id': f'synthetic-thread-{index}', 'updatedAt': index}
            for index in range(6)
        ]

        outputs, partial = _read_codex_latest_outputs(client, threads)
        self.assertFalse(partial)
        self.assertEqual(len(client.calls), 4)
        self.assertEqual(
            [thread_id for _, thread_id, _ in client.calls],
            ['synthetic-thread-5', 'synthetic-thread-4', 'synthetic-thread-3', 'synthetic-thread-2'],
        )
        self.assertEqual(set(outputs), {thread_id for _, thread_id, _ in client.calls})
        self.assertTrue(all(method == 'thread/read' for method, _, _ in client.calls))
        self.assertTrue(all(timeout == 1.5 for _, _, timeout in client.calls))

        cached, cache_partial = _read_codex_latest_outputs(client, threads)
        self.assertFalse(cache_partial)
        self.assertEqual(len(client.calls), 4)
        self.assertEqual(cached, outputs)

    def test_claude_tail_reads_only_last_assistant_text_and_skips_user_and_tools(self):
        session_id = 'synthetic-session-id'
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_dir = Path(temp_dir) / 'projects'
            transcript = projects_dir / 'synthetic-project' / f'{session_id}.jsonl'
            transcript.parent.mkdir(parents=True)
            entries = [
                {'type': 'user', 'message': {'content': 'user prompt'}},
                {
                    'type': 'assistant',
                    'message': {
                        'content': [
                            {'type': 'thinking', 'thinking': 'private reasoning'},
                            {'type': 'text', 'text': 'last assistant answer token=synthetic-secret'},
                        ]
                    },
                },
                {'type': 'tool_result', 'content': 'tool output must not be shown'},
            ]
            transcript.write_text(
                ''.join(json.dumps(entry) + '\n' for entry in entries),
                encoding='utf-8',
            )

            output = _read_claude_last_agent_output(session_id, projects_dir=projects_dir)

        self.assertEqual(output, 'last assistant answer [凭据已隐藏]')
        records, _ = normalize_claude_agents(
            [
                {
                    'id': 'synthetic-agent-id',
                    'sessionId': session_id,
                    'state': 'active',
                    'name': 'Synthetic Claude session',
                    'cwd': 'C:/Projects/ClaudeProject',
                }
            ],
            observed_at=NOW,
            sequence=1,
            latest_outputs={session_id: output},
        )
        self.assertEqual(records[0]['summary'], output)
        self.assertEqual(records[0]['last_output_kind'], 'agent_message')

    def test_claude_output_join_skips_shared_session_ids(self):
        payload = [
            {'id': 'agent-a', 'sessionId': 'shared-session-id'},
            {'id': 'agent-b', 'sessionId': 'shared-session-id'},
        ]
        with patch('live_sources._read_claude_last_agent_output') as read_output:
            outputs = _read_claude_latest_outputs(payload)

        self.assertEqual(outputs, {})
        read_output.assert_not_called()

    def test_each_source_session_page_exposes_name_status_project_and_output_truthfully(self):
        codex_records, _ = normalize_codex_threads(
            {
                'data': [
                    {
                        'id': 'codex-cli-id',
                        'name': 'Synthetic CLI session',
                        'cwd': 'C:/Projects/CodexProject',
                        'preview': 'A recent thread preview',
                        'status': {'type': 'active', 'activeFlags': []},
                    }
                ]
            },
            observed_at=NOW,
            sequence=1,
            agent_outputs={'codex-cli-id': 'A confirmed Codex CLI response'},
        )
        claude_records, _ = normalize_claude_agents(
            [
                {
                    'id': 'claude-id',
                    'sessionId': 'claude-id',
                    'name': 'Synthetic Claude session',
                    'cwd': 'C:/Projects/ClaudeProject',
                    'state': 'active',
                }
            ],
            observed_at=NOW,
            sequence=1,
            latest_outputs={'claude-id': 'A confirmed Claude Code response'},
        )
        app_records, _ = normalize_codex_app_snapshot(
            {
                'snapshot_version': 1,
                'source_health': 'online',
                'threads': [
                    {
                        'thread_id': '00000000-0000-4000-8000-000000000010',
                        'title': 'Synthetic App session',
                        'status': 'active',
                        'project_label': 'AppProject',
                        'last_agent_output': 'A confirmed Agent response',
                        'last_output_kind': 'agent_message',
                    }
                ],
            },
            observed_at=NOW,
            sequence=1,
        )
        projection = aggregate_activities(codex_records + claude_records + app_records, now=NOW)
        projection.update(
            {
                'source_health': {'codex': 'online', 'codex-app': 'online', 'claude-code': 'online'},
                'source_labels': LIVE_SOURCE_LABELS,
                'data_mode_label': '本机实时只读',
            }
        )

        expectations = {
            'codex': ('Synthetic CLI session', '项目：CodexProject', '最近 Agent 输出：A confirmed Codex CLI response'),
            'claude-code': ('Synthetic Claude session', '项目：ClaudeProject', '最近 Agent 输出：A confirmed Claude Code response'),
            'codex-app': ('Synthetic App session', '项目：AppProject', '最近 Agent 输出：A confirmed Agent response'),
        }
        for source_id, (name, project, output) in expectations.items():
            with self.subTest(source=source_id):
                scene, _, _ = build_global_overview_scene(
                    projection,
                    GlobalOverviewState(source=source_id),
                )
                row = scene['data']['sessions'][0]
                self.assertEqual(row['name'], name)
                self.assertTrue(row['status'])
                self.assertEqual(row['project'], project)
                self.assertEqual(row['output'], output)
                nodes = list(walk_nodes(scene['root']))
                self.assertTrue(any(node['id'].startswith('global-session-name-') for node in nodes))
                self.assertTrue(any(node['id'].startswith('global-session-status-') for node in nodes))
                self.assertTrue(any(node['id'].startswith('global-session-project-') for node in nodes))
                self.assertTrue(any(node['id'].startswith('global-session-output-') for node in nodes))
                serialized = json.dumps(scene, ensure_ascii=False)
                self.assertNotIn('C:/Projects/', serialized)
                self.assertNotIn('codex-cli-id', serialized)
                self.assertNotIn('claude-id', serialized)

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


class LocalCodexAppStateTests(unittest.TestCase):
    def test_local_desktop_state_shows_only_desktop_metadata_and_verified_agent_output(self):
        desktop_id = '00000000-0000-4000-8000-000000000101'
        cli_id = '00000000-0000-4000-8000-000000000102'
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / '.codex'
            create_codex_app_state_fixture(
                root,
                [
                    {
                        'id': desktop_id,
                        'title': 'Synthetic Desktop title',
                        'name': 'Synthetic Desktop session',
                        'cwd': 'C:/Private/SyntheticProject',
                        'originator': 'Codex Desktop',
                        'updated_at_ms': 200,
                        'agent_output': 'Synthetic Agent reply token=synthetic-secret C:\\Private\\note.md',
                    },
                    {
                        'id': cli_id,
                        'title': 'Synthetic CLI session',
                        'cwd': 'C:/Private/OtherProject',
                        'originator': 'Codex CLI',
                        'updated_at_ms': 100,
                    },
                    {
                        'id': '00000000-0000-4000-8000-000000000103',
                        'title': 'Archived Desktop session',
                        'cwd': 'C:/Private/ArchivedProject',
                        'originator': 'Codex Desktop',
                        'archived': 1,
                        'updated_at_ms': 50,
                    },
                    {
                        'id': '00000000-0000-4000-8000-000000000104',
                        'title': 'Synthetic Desktop without output',
                        'cwd': 'C:/Private/SecondProject',
                        'originator': 'Codex Desktop',
                        'updated_at_ms': 150,
                    },
                ],
            )
            records, health = read_codex_app_local_threads(
                observed_at=NOW,
                sequence=6,
                codex_root=root,
            )

        self.assertEqual(health, 'local_state')
        self.assertEqual(len(records), 2)
        record = next(item for item in records if item['codex_app_thread_id'] == desktop_id)
        self.assertEqual(record['source_type'], 'codex-app')
        self.assertEqual(record['provider_id'], 'codex-app-local-state')
        self.assertEqual(record['display_name'], 'Synthetic Desktop session')
        self.assertEqual(record['project_label'], 'SyntheticProject')
        self.assertEqual(record['normalized_status'], 'unknown')
        self.assertEqual(record['last_output_kind'], 'agent_message')
        self.assertEqual(
            record['summary'],
            'Synthetic Agent reply [凭据已隐藏] [本机路径]',
        )
        ACTIVITY_VALIDATOR.validate(record)

        projection = aggregate_activities(records, now=NOW)
        projection.update(
            {
                'source_health': {
                    'codex': 'online',
                    'codex-app': 'local_state',
                    'claude-code': 'online',
                },
                'source_labels': LIVE_SOURCE_LABELS,
                'data_mode_label': '本机 Codex Desktop 状态库只读',
            }
        )
        scene, _, _ = build_global_overview_scene(projection, GlobalOverviewState())
        preview = next(
            item for item in scene['data']['codex_app_preview']
            if item['project'] == '项目：SyntheticProject'
        )
        self.assertEqual(preview['status'], '状态未知')
        self.assertEqual(
            preview['output'],
            '最近 Agent 输出：Synthetic Agent reply [凭据已隐藏] [本机路径]',
        )
        self.assertEqual(scene['data']['summary']['codex_app_health'], '本机状态库可读')
        self.assertEqual(scene['data']['summary']['codex_parallel'], '—')
        app_scene, _, _ = build_global_overview_scene(
            projection,
            GlobalOverviewState(source='codex-app'),
        )
        source_summary = next(
            node['props']['text']
            for node in walk_nodes(app_scene['root'])
            if node['id'] == 'global-source-summary'
        )
        self.assertIn('status unknown', source_summary)
        serialized = json.dumps(scene, ensure_ascii=False)
        for forbidden in (
            desktop_id,
            cli_id,
            'C:/Private/',
            'synthetic-secret',
            'synthetic private prompt',
            'synthetic tool output',
        ):
            self.assertNotIn(forbidden, serialized)

    def test_bridge_enriches_local_rows_without_duplicate_threads(self):
        desktop_id = '00000000-0000-4000-8000-000000000111'
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / '.codex'
            create_codex_app_state_fixture(
                root,
                [{
                    'id': desktop_id,
                    'title': 'Synthetic local title',
                    'cwd': 'C:/Projects/SyntheticProject',
                    'originator': 'Codex Desktop',
                    'updated_at_ms': 200,
                }],
            )
            local_records, local_health = read_codex_app_local_threads(
                observed_at=NOW,
                sequence=1,
                codex_root=root,
            )
        self.assertEqual(local_health, 'local_state')
        app_projection = aggregate_activities(local_records, now=NOW)
        app_projection.update(
            {
                'source_health': {'codex': 'online', 'codex-app': 'local_state', 'claude-code': 'online'},
                'source_labels': LIVE_SOURCE_LABELS,
                'data_mode_label': '本机 Codex Desktop 状态库只读',
            }
        )
        previous = LiveSnapshot(
            app_projection,
            {'codex-app': local_records, 'codex': [], 'claude-code': []},
            1,
            {'codex-app': NOW},
        )

        merged = merge_codex_app_snapshot(
            previous,
            {
                'snapshot_version': 1,
                'source_health': 'online',
                'captured_at': '2026-10-29T08:00:00Z',
                'threads': [
                    {
                        'thread_id': desktop_id,
                        'title': 'Connector title',
                        'status': 'active',
                        'project_label': 'Connector project',
                        'last_agent_output': 'Connector Agent output',
                        'last_output_kind': 'agent_message',
                    }
                ],
            },
            sequence=2,
            now=NOW,
            links_enabled=True,
        )

        records = merged.records_by_source['codex-app']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['provider_id'], 'codex-app-connector')
        self.assertEqual(records[0]['display_name'], 'Connector title')
        self.assertEqual(records[0]['normalized_status'], 'running')
        self.assertEqual(records[0]['summary'], 'Connector Agent output')
        self.assertEqual(merged.projection['source_health']['codex-app'], 'online')


class LiveSourceFailureTests(unittest.TestCase):
    def setUp(self):
        local_state = patch(
            'live_sources.read_codex_app_local_threads',
            return_value=([], 'unavailable'),
        )
        local_state.start()
        self.addCleanup(local_state.stop)

    # 🤖【2026-10-29】回归：延迟到达与未来的来源时间不能冒充新鲜快照
    def test_codex_app_capture_time_controls_freshness_and_expiry_boundary(self):
        with (
            patch('live_sources.read_codex_threads', return_value=([], 'online')),
            patch('live_sources.read_claude_agents', return_value=([], 'online')),
        ):
            base = load_live_snapshot(sequence=1, now=NOW)

        payload = {
            'snapshot_version': 1,
            'source_health': 'online',
            'captured_at': '2026-10-29T07:59:30Z',
            'threads': [
                {
                    'thread_id': '00000000-0000-4000-8000-000000000001',
                    'title': 'Synthetic stale thread',
                    'status': 'active',
                    'project_label': 'Synthetic project',
                    'last_agent_output': 'Synthetic output',
                    'last_output_kind': 'agent_message',
                }
            ],
        }

        merged = merge_codex_app_snapshot(
            base,
            payload,
            sequence=2,
            now=NOW,
            links_enabled=False,
        )

        app_session = next(
            session for session in merged.projection['sessions']
            if session['source_type_label'] == 'Codex App'
        )
        self.assertEqual(merged.projection['source_health']['codex-app'], 'online')
        self.assertEqual(merged.projection['source_age_seconds']['codex-app'], 30)
        self.assertEqual(merged.projection['source_freshness']['codex-app'], 'stale')
        self.assertEqual(app_session['freshness'], 'stale')
        self.assertEqual(app_session['normalized_status'], 'stale')

    def test_codex_app_invalid_capture_time_fails_closed_for_its_source(self):
        with (
            patch('live_sources.read_codex_threads', return_value=([], 'online')),
            patch('live_sources.read_claude_agents', return_value=([], 'online')),
        ):
            base = load_live_snapshot(sequence=1, now=NOW)

        for captured_at in (
            '2026-10-29T08:00:01Z',
            'not-a-timestamp',
            '2026-10-29T08:00:00',
        ):
            with self.subTest(captured_at=captured_at):
                payload = {
                    'snapshot_version': 1,
                    'source_health': 'online',
                    'captured_at': captured_at,
                    'threads': [],
                }
                with self.assertRaises(SourceReadError) as error:
                    merge_codex_app_snapshot(
                        base,
                        payload,
                        sequence=2,
                        now=NOW,
                        links_enabled=False,
                    )
                self.assertEqual(error.exception.source_id, 'codex-app')

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
        self.assertNotIn('C:/private', serialized)
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
        self.assertIn('private title', serialized)
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
