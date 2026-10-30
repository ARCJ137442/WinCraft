import json
import os
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

from activity_board import ACTIVITY_VALIDATOR, MAX_ACTIVITIES, aggregate_activities  # noqa: E402
from global_overview import (  # noqa: E402
    GlobalOverviewState,
    build_global_overview_scene,
    reconcile_view_state,
)
from live_sources import (  # noqa: E402
    LIVE_SOURCE_LABELS,
    SourceReadError,
    load_live_snapshot,
    normalize_claude_agents,
    normalize_codex_threads,
    normalize_live_source_selection,
    summarize_live_snapshot,
    _codex_last_agent_output,
    _read_claude_latest_outputs,
    _read_claude_last_agent_output,
    _read_codex_rollout_agent_output,
    _read_codex_latest_outputs,
    _activity_record,
    _claude_code_process_running,
    _codex_app_process_running,
    _normalized_executable_path,
    _local_process_states,
    read_codex_app_local_threads,
    read_claude_local_sessions,
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
        process_states = patch(
            'live_sources._local_process_states',
            return_value={'codex-app': True, 'claude-code': True},
        )
        process_states.start()
        self.addCleanup(process_states.stop)
        local_state = patch(
            'live_sources.read_codex_app_local_threads',
            return_value=([], 'unavailable'),
        )
        local_state.start()
        self.addCleanup(local_state.stop)

    def test_combined_local_sources_respect_global_limit_and_keep_parent_rows(self):
        codex_records = [
            _activity_record(
                source_id='codex-app',
                raw_id=f'codex-app-{index}',
                parent_raw_id=None,
                status='unknown',
                normalized_status='unknown',
                authority='unknown',
                sequence=index + 1,
                observed_at=NOW,
                provenance='local-state-db',
            )
            for index in range(129)
        ]
        codex_records.extend((
            _activity_record(
                source_id='codex-app',
                raw_id='codex-app-parent',
                parent_raw_id=None,
                status='unknown',
                normalized_status='unknown',
                authority='unknown',
                sequence=1000,
                observed_at=NOW,
                provenance='local-state-db',
            ),
            _activity_record(
                source_id='codex-app',
                raw_id='codex-app-child',
                parent_raw_id='codex-app-parent',
                status='unknown',
                normalized_status='unknown',
                authority='unknown',
                sequence=0,
                observed_at=NOW,
                provenance='local-state-db',
            ),
        ))
        for index, record in enumerate(codex_records):
            record['codex_app_thread_id'] = (
                f'00000000-0000-4000-8000-{index:012d}'
            )
        claude_records = [
            _activity_record(
                source_id='claude-code',
                raw_id=f'claude-code-{index}',
                parent_raw_id=None,
                status='unknown',
                normalized_status='unknown',
                authority='unknown',
                sequence=index,
                observed_at=NOW,
                provenance='approved-log',
            )
            for index in range(130)
        ]

        with (
            patch(
                'live_sources.read_codex_app_local_threads',
                return_value=(codex_records, 'local_state'),
            ),
            patch(
                'live_sources.read_claude_local_sessions',
                return_value=(claude_records, 'local_state'),
            ),
        ):
            snapshot = load_live_snapshot(
                sequence=1,
                now=NOW,
                enabled_sources=('codex-app', 'claude-code'),
            )

        self.assertEqual(
            snapshot.projection['summary']['total_sessions'],
            MAX_ACTIVITIES,
            msg=(
                f"source counts={{{', '.join(f'{key}:{len(value)}' for key, value in snapshot.records_by_source.items())}}}, "
                f"data health={snapshot.projection['source_data_health']}"
            ),
        )
        self.assertEqual(
            snapshot.projection['source_data_health']['codex-app'],
            'partial',
        )
        self.assertEqual(
            snapshot.projection['source_data_health']['claude-code'],
            'partial',
        )
        codex_parent_ids = {
            record['session_id']
            for record in snapshot.records_by_source['codex-app']
        }
        codex_child = next(
            record
            for record in snapshot.records_by_source['codex-app']
            if record['parent_session_id'] is not None
        )
        self.assertIn(codex_child['parent_session_id'], codex_parent_ids)

    def test_source_freshness_tracks_last_success_and_disconnect_age(self):
        with (
            patch('live_sources.read_codex_threads', return_value=([], 'online')),
            patch('live_sources.read_claude_local_sessions', return_value=([], 'online')),
        ):
            first = load_live_snapshot(sequence=1, now=NOW)

        with (
            patch(
                'live_sources.read_codex_threads',
                side_effect=SourceReadError('codex', 'timeout'),
            ),
            patch(
                'live_sources.read_claude_local_sessions',
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
            patch('live_sources._local_process_states', return_value={'codex-app': False, 'claude-code': False}),
            patch('live_sources.read_codex_app_local_threads', return_value=(records, 'local_state')),
            patch('live_sources.read_codex_threads', return_value=([], 'online')),
            patch('live_sources.read_claude_local_sessions', return_value=([], 'local_state')),
        ):
            live_snapshot = load_live_snapshot(sequence=7, now=NOW)
        self.assertEqual(live_snapshot.projection['source_health']['codex-app'], 'offline')
        self.assertEqual(live_snapshot.projection['source_data_health']['codex-app'], 'local_state')
        self.assertEqual(
            live_snapshot.projection['data_mode_label'],
            'Codex CLI 本机状态库只读 · Codex App 状态库与 rollout 只读 · 进程离线 · Claude Code 会话索引只读 · 进程离线',
        )
        self.assertEqual(len(live_snapshot.records_by_source['codex-app']), 2)

        projection = aggregate_activities(records, now=NOW)
        projection.update(
            {
                'source_health': {'codex': 'online', 'codex-app': 'offline', 'claude-code': 'offline'},
                'source_data_health': {
                    'codex': 'not_applicable',
                    'codex-app': 'local_state',
                    'claude-code': 'local_state',
                },
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
        self.assertEqual(scene['data']['summary']['codex_app_health'], '进程离线')
        self.assertEqual(scene['data']['summary']['codex_app_data_health'], '本机数据可读')
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
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_root = Path(temp_dir) / '.codex'
            create_codex_app_state_fixture(
                codex_root,
                [{
                    'id': '00000000-0000-4000-8000-000000000010',
                    'title': 'Synthetic App session',
                    'name': 'Synthetic App session',
                    'cwd': 'C:/Projects/AppProject',
                    'originator': 'Codex Desktop',
                    'updated_at_ms': 100,
                    'agent_output': 'A confirmed Agent response',
                }],
            )
            app_records, app_health = read_codex_app_local_threads(
                observed_at=NOW,
                sequence=1,
                codex_root=codex_root,
            )
        self.assertEqual(app_health, 'local_state')
        projection = aggregate_activities(codex_records + claude_records + app_records, now=NOW)
        projection.update(
            {
                'source_health': {'codex': 'online', 'codex-app': 'offline', 'claude-code': 'offline'},
                'source_data_health': {
                    'codex': 'not_applicable',
                    'codex-app': 'local_state',
                    'claude-code': 'local_state',
                },
                'source_labels': LIVE_SOURCE_LABELS,
                'data_mode_label': '本机状态文件只读',
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
    def setUp(self):
        process_states = patch(
            'live_sources._local_process_states',
            return_value={'codex-app': False, 'claude-code': False},
        )
        process_states.start()
        self.addCleanup(process_states.stop)

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
                    'codex-app': 'offline',
                    'claude-code': 'online',
                },
                'source_data_health': {
                    'codex': 'not_applicable',
                    'codex-app': 'local_state',
                    'claude-code': 'local_state',
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
        self.assertEqual(scene['data']['summary']['codex_app_health'], '进程离线')
        self.assertEqual(scene['data']['summary']['codex_app_data_health'], '本机数据可读')
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

class LiveSourceFailureTests(unittest.TestCase):
    def setUp(self):
        process_states = patch(
            'live_sources._local_process_states',
            return_value={'codex-app': True, 'claude-code': True},
        )
        process_states.start()
        self.addCleanup(process_states.stop)
        local_state = patch(
            'live_sources.read_codex_app_local_threads',
            return_value=([], 'unavailable'),
        )
        local_state.start()
        self.addCleanup(local_state.stop)

    # 🤖【2026-10-29】回归：延迟到达与未来的来源时间不能冒充新鲜快照
    def test_refresh_preserves_selection_when_a_session_disappears(self):
        state = GlobalOverviewState(
            source='claude-code',
            selected_identity=('device', 'provider', 'instance', 'old-session'),
            page=2,
            revision=7,
        )

        next_state = reconcile_view_state({'sessions': []}, state)

        self.assertEqual(next_state.source, 'claude-code')
        self.assertEqual(next_state.selected_identity, state.selected_identity)
        self.assertTrue(next_state.selection_missing)
        self.assertEqual(next_state.page, 2)
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
            patch('live_sources.read_claude_local_sessions', return_value=(claude_records, 'online')),
        ):
            first = load_live_snapshot(sequence=1, now=NOW)

        with (
            patch('live_sources.read_codex_threads', return_value=(codex_records, 'online')),
            patch(
                'live_sources.read_claude_local_sessions',
                side_effect=SourceReadError('claude-code', 'timeout'),
            ),
        ):
            second = load_live_snapshot(first, sequence=2, now=NOW)

        self.assertEqual(second.projection['source_health'], {
            'codex': 'online',
            'codex-app': 'online',
            'claude-code': 'online',
        })
        self.assertEqual(second.projection['source_data_health'], {
            'codex': 'not_applicable',
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
                'live_sources.read_claude_local_sessions',
                side_effect=SourceReadError('claude-code', 'cli_failed'),
            ),
        ):
            snapshot = load_live_snapshot(sequence=1, now=NOW)

        self.assertEqual(snapshot.projection['source_health']['claude-code'], 'online')
        self.assertEqual(snapshot.projection['source_data_health']['claude-code'], 'unavailable')
        self.assertEqual(snapshot.projection['source_health']['codex'], 'online')
        self.assertEqual(snapshot.projection['sessions'], [])

    def test_selected_sources_do_not_read_or_retain_stalled_codex_app_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_root = Path(temp_dir) / '.codex'
            create_codex_app_state_fixture(
                codex_root,
                [{
                    'id': '00000000-0000-4000-8000-000000000001',
                    'title': 'Synthetic App row',
                    'name': 'Synthetic App row',
                    'cwd': 'C:/Projects/SyntheticProject',
                    'originator': 'Codex Desktop',
                    'updated_at_ms': 1,
                    'agent_output': 'Synthetic local Agent output',
                }],
            )
            with (
                patch(
                    'live_sources.read_codex_app_local_threads',
                    side_effect=lambda **kwargs: read_codex_app_local_threads(
                        codex_root=codex_root,
                        **kwargs,
                    ),
                ),
                patch('live_sources.read_codex_threads', return_value=([], 'online')),
                patch('live_sources.read_claude_local_sessions', return_value=([], 'local_state')),
            ):
                previous = load_live_snapshot(sequence=1, now=NOW)

            with (
                patch('live_sources.read_codex_app_local_threads') as app_reader,
                patch('live_sources.read_codex_threads', return_value=([], 'online')),
                patch('live_sources.read_claude_local_sessions', return_value=([], 'local_state')),
            ):
                selected = load_live_snapshot(
                    previous,
                    sequence=2,
                    now=NOW + timedelta(seconds=1),
                    enabled_sources=('codex', 'claude-code'),
                )

        app_reader.assert_not_called()
        self.assertEqual(selected.records_by_source['codex-app'], [])
        self.assertNotIn('codex-app', selected.source_observed_at)
        self.assertEqual(selected.projection['source_health']['codex-app'], 'not_requested')
        self.assertFalse(any(session['source_type_label'] == 'Codex App' for session in selected.projection['sessions']))
        self.assertIn('Codex App 本轮未查询', selected.projection['data_mode_label'])

    def test_live_source_selection_is_nonempty_unique_and_known(self):
        self.assertEqual(
            normalize_live_source_selection(('codex', 'claude-code')),
            ('codex', 'claude-code'),
        )
        for selection in ((), ('codex', 'codex'), ('codex', 'unknown')):
            with self.subTest(selection=selection):
                with self.assertRaises(ValueError):
                    normalize_live_source_selection(selection)

    def test_selected_sources_reject_empty_duplicate_and_unknown_ids_before_reading(self):
        for selection in ((), ('codex', 'codex'), ('codex', 'unknown')):
            with self.subTest(selection=selection):
                with (
                    patch('live_sources.read_codex_app_local_threads') as app_reader,
                    patch('live_sources.read_codex_threads') as codex_reader,
                    patch('live_sources.read_claude_local_sessions') as claude_reader,
                    self.assertRaises(ValueError),
                ):
                    load_live_snapshot(sequence=1, now=NOW, enabled_sources=selection)
                app_reader.assert_not_called()
                codex_reader.assert_not_called()
                claude_reader.assert_not_called()

    def test_snapshot_log_summary_contains_only_aggregate_statuses(self):
        records, _ = normalize_claude_agents(
            [{'id': 'private-id', 'state': 'blocked', 'name': 'private title'}],
            observed_at=NOW,
            sequence=1,
        )
        with (
            patch('live_sources.read_codex_threads', return_value=([], 'online')),
            patch('live_sources.read_claude_local_sessions', return_value=(records, 'online')),
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
                'codex-app': 'offline',
                'claude-code': 'partial',
            },
            'source_data_health': {
                'codex': 'not_applicable',
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
        self.assertEqual(scene['data']['summary']['codex_app_health'], '进程离线')
        self.assertEqual(scene['data']['summary']['codex_app_data_health'], '数据不可用')
        serialized = json.dumps(scene, ensure_ascii=False)
        self.assertIn('本机实时只读', serialized)
        self.assertIn('Codex CLI · 本机状态库', serialized)
        self.assertIn('Codex App', serialized)
        self.assertIn('CLI 可查询', serialized)
        self.assertIn('进程离线', serialized)
        self.assertIn('CLI 部分可用', serialized)
        self.assertIn('已过期 · 上次成功 31 秒前', serialized)
        self.assertIn('读取于 5 秒前', serialized)
        self.assertIn('尚未读取到本机状态', serialized)
        self.assertIn('已过期 · 上次成功 31 秒前', serialized)
        self.assertIn('阻塞', serialized)
        self.assertNotIn('private-id', serialized)
        self.assertIn('private title', serialized)
        self.assertNotIn('source_status', serialized)

    def test_codex_app_title_is_clickable_only_with_host_thread_navigation_capability(self):
        thread_id = '00000000-0000-4000-8000-000000000003'
        with tempfile.TemporaryDirectory() as temp_dir:
            codex_root = Path(temp_dir) / '.codex'
            create_codex_app_state_fixture(
                codex_root,
                [{
                    'id': thread_id,
                    'title': 'Synthetic Codex App thread',
                    'name': 'Synthetic Codex App thread',
                    'cwd': 'C:/Projects/SyntheticProject',
                    'originator': 'Codex Desktop',
                    'updated_at_ms': 100,
                    'agent_output': 'Synthetic output',
                }],
            )
            records, data_health = read_codex_app_local_threads(
                observed_at=NOW,
                sequence=1,
                codex_root=codex_root,
            )
        self.assertEqual(data_health, 'local_state')
        from activity_board import aggregate_activities

        projection = aggregate_activities(records, now=NOW)
        projection.update({
            'source_health': {'codex': 'online', 'codex-app': 'online', 'claude-code': 'offline'},
            'source_data_health': {
                'codex': 'not_applicable',
                'codex-app': 'local_state',
                'claude-code': 'local_state',
            },
            'source_labels': {'codex': 'Codex CLI', 'codex-app': 'Codex App', 'claude-code': 'Claude Code'},
            'data_mode_label': 'Codex App 本机文件只读',
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


class ClaudeLocalHistoryTests(unittest.TestCase):
    def setUp(self):
        process_states = patch(
            'live_sources._local_process_states',
            return_value={'codex-app': False, 'claude-code': False},
        )
        process_states.start()
        self.addCleanup(process_states.stop)

    def create_history(self, config_dir: Path, session_id: str) -> Path:
        project_dir = config_dir / 'projects' / 'C--Projects-PrivateProject'
        project_dir.mkdir(parents=True)
        transcript = project_dir / f'{session_id}.jsonl'
        entries = [
            {
                'type': 'custom-title',
                'sessionId': session_id,
                'customTitle': 'Synthetic Claude work session',
            },
            {
                'type': 'user',
                'sessionId': session_id,
                'cwd': 'C:/Projects/PrivateProject',
                'message': {'content': 'Synthetic private prompt'},
            },
            {
                'type': 'assistant',
                'sessionId': session_id,
                'cwd': 'C:/Projects/PrivateProject',
                'message': {
                    'content': [
                        {'type': 'thinking', 'thinking': 'synthetic hidden reasoning'},
                        {
                            'type': 'text',
                            'text': 'Synthetic final answer token=synthetic-secret C:\\Private\\note.md',
                        },
                    ],
                    'stop_reason': 'end_turn',
                },
            },
            {'type': 'tool_result', 'content': 'Synthetic tool output'},
        ]
        transcript.write_text(
            ''.join(json.dumps(entry) + '\n' for entry in entries),
            encoding='utf-8',
        )
        (project_dir / 'sessions-index.json').write_text(
            json.dumps({
                'version': 1,
                'originalPath': 'C:/Projects/PrivateProject',
                'entries': [{
                    'sessionId': session_id,
                    'summary': 'Synthetic Claude work session',
                    'projectPath': 'C:/Projects/PrivateProject',
                    'fullPath': 'C:/untrusted/outside/session.jsonl',
                    'fileMtime': 1,
                    'isSidechain': False,
                }],
            }),
            encoding='utf-8',
        )
        return transcript

    def test_offline_process_keeps_local_history_without_spawning_claude(self):
        session_id = '00000000-0000-4000-8000-000000000201'
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / '.claude'
            transcript = self.create_history(config_dir, session_id)
            with (
                patch('live_sources.subprocess.run', side_effect=AssertionError('must not spawn CLI')),
                patch('live_sources.subprocess.Popen', side_effect=AssertionError('must not spawn CLI')),
                patch('live_sources.read_codex_app_local_threads', return_value=([], 'local_state')),
                patch('live_sources.read_codex_threads', return_value=([], 'online')),
                patch(
                    'live_sources.read_claude_local_sessions',
                    side_effect=lambda **kwargs: read_claude_local_sessions(
                        config_dir=config_dir,
                        **kwargs,
                    ),
                ),
            ):
                records, data_health = read_claude_local_sessions(
                    observed_at=NOW,
                    sequence=2,
                    config_dir=config_dir,
                )
                snapshot = load_live_snapshot(sequence=3, now=NOW)

        self.assertEqual(data_health, 'local_state')
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['display_name'], 'Synthetic Claude work session')
        self.assertEqual(records[0]['project_label'], 'PrivateProject')
        self.assertEqual(
            records[0]['summary'],
            'Synthetic final answer [凭据已隐藏] [本机路径]',
        )
        self.assertEqual(records[0]['normalized_status'], 'unknown')
        self.assertEqual(snapshot.projection['source_health']['claude-code'], 'offline')
        self.assertEqual(snapshot.projection['source_data_health']['claude-code'], 'local_state')
        self.assertEqual(len(snapshot.records_by_source['claude-code']), 1)
        serialized = json.dumps(snapshot.projection, ensure_ascii=False)
        for forbidden in (
            session_id,
            'C:/untrusted/outside',
            'Synthetic private prompt',
            'Synthetic tool output',
            'synthetic hidden reasoning',
            'synthetic-secret',
            'C:\\Private',
        ):
            self.assertNotIn(forbidden, serialized)

    def test_session_file_with_mismatched_identity_is_skipped_and_marks_partial(self):
        session_id = '00000000-0000-4000-8000-000000000202'
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / '.claude'
            project_dir = config_dir / 'projects' / 'project'
            project_dir.mkdir(parents=True)
            (project_dir / f'{session_id}.jsonl').write_text(
                json.dumps({
                    'type': 'user',
                    'sessionId': '00000000-0000-4000-8000-000000000299',
                    'cwd': 'C:/Projects/SafeProject',
                }) + '\n',
                encoding='utf-8',
            )
            records, data_health = read_claude_local_sessions(
                observed_at=NOW,
                sequence=1,
                config_dir=config_dir,
            )

        self.assertEqual(records, [])
        self.assertEqual(data_health, 'partial')


class LocalProcessDetectionTests(unittest.TestCase):
    def test_codex_app_requires_its_installed_image_and_desktop_parent(self):
        with patch.dict(os.environ, {'LOCALAPPDATA': 'C:/Local'}):
            app_exe = 'C:/Local/OpenAI/Codex/bin/version/codex.exe'
            processes = [
                {'pid': 10, 'ppid': 1, 'name': 'ChatGPT.exe', 'exe': 'C:/Program Files/ChatGPT.exe'},
                {'pid': 11, 'ppid': 10, 'name': 'codex.exe', 'exe': app_exe},
            ]
            self.assertTrue(_codex_app_process_running(processes))
            processes[1]['ppid'] = 1
            self.assertFalse(_codex_app_process_running(processes))

    def test_claude_process_matches_only_the_resolved_installed_image(self):
        executable = (
            'C:/Users/test/AppData/Roaming/npm/node_modules/'
            '@anthropic-ai/claude-code/bin/claude.exe'
        )
        with patch(
            'live_sources._claude_code_executable_paths',
            return_value={_normalized_executable_path(executable)},
        ):
            self.assertTrue(_claude_code_process_running([
                {'pid': 9, 'name': 'claude.exe', 'exe': executable},
            ]))
            self.assertFalse(_claude_code_process_running([
                {'pid': 10, 'name': 'claude.exe', 'exe': 'C:/Other/claude.exe'},
            ]))

    def test_process_enumeration_failure_is_unknown_not_offline(self):
        with patch('live_sources._local_process_snapshot', return_value=None):
            self.assertEqual(_local_process_states(), {'codex-app': None, 'claude-code': None})


if __name__ == '__main__':
    unittest.main()
