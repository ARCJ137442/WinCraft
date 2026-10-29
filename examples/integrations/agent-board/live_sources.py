'''只读采集 Codex CLI 与 Claude Code 的活动状态
- 🎯将官方 CLI 状态转换为受限的 WinCraft activity 投影
- ⚠️不读取会话预览、提示词、工作目录或完整日志
'''
from __future__ import annotations

import hashlib
import json
import queue
import re
import shutil
import subprocess
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import UUID

from activity_board import MAX_ACTIVITIES, aggregate_activities

CODEX_COMMAND: str = 'codex'
'''📜Codex CLI 的可执行文件查找名'''
CLAUDE_COMMAND: str = 'claude'
'''📜Claude Code CLI 的可执行文件查找名'''
CODEX_THREAD_PAGE_LIMIT: int = 100
'''📜每次 Codex app-server thread/list 请求的最大页长'''
CODEX_MAX_THREAD_PAGES: int = 10
'''📜避免无界读取本地线程元数据的分页上限'''
CODEX_RPC_TIMEOUT_SECONDS: float = 8.0
'''📜单次 Codex app-server RPC 的等待上限'''
CLI_TIMEOUT_SECONDS: float = 8.0
'''📜Claude Code CLI 只读状态查询的等待上限'''
SOURCE_SNAPSHOT_TTL_SECONDS: int = 30
'''📜真实状态快照的有效期；超过后投影为过期'''
SOURCE_SEQUENCE_STRIDE: int = 1024
'''📜为来源列表顺序和快照代次保留不重叠的 sequence 范围'''
LIVE_MAPPING_VERSION: str = '1'
'''📜本地 CLI 状态到 activity draft 的映射版本'''
KNOWN_CLAUDE_STATES = frozenset({'active', 'blocked', 'idle'})
'''📜Claude Code agents --json 已识别的来源状态集合'''
KNOWN_CODEX_STATUS_TYPES = frozenset({'active', 'idle', 'notLoaded', 'systemError'})
'''📜Codex app-server ThreadStatus 已识别的来源状态集合'''
LIVE_SOURCE_LABELS = {
    'codex': 'Codex CLI · 本机状态库',
    'codex-app': 'Codex App',
    'claude-code': 'Claude Code',
}
'''📜明确区分 Codex CLI 本机状态库与 Codex App 连接器'''


class SourceReadError(RuntimeError):
    '''表示某个 Harness 的只读状态读取失败
    - 📌reason_code 是固定错误类别，不携带命令输出或会话内容
    '''

    def __init__(self, source_id: str, reason_code: str) -> None:
        super().__init__(f'{source_id}:{reason_code}')
        self.source_id = source_id
        self.reason_code = reason_code


@dataclass(frozen=True)
class LiveSnapshot:
    '''保存一轮受限的实时来源投影
    - 📌projection 仅含 UI 所需状态与来源健康
    - 📌records_by_source 保存已脱敏的活动记录，用于单来源故障时标记 stale
    - 📌sequence 是本 Provider 内递增的采样序号
    '''

    projection: dict[str, Any]
    '''投影给通用 renderer 的状态'''
    records_by_source: dict[str, list[dict[str, Any]]]
    '''只含哈希身份和来源状态，不含名称、路径、预览或日志'''
    sequence: int
    '''当前采样序号'''
    source_observed_at: dict[str, datetime]
    '''每个来源最近一次成功快照的本机接收时刻'''


class _CodexAppServer:
    '''通过本地 stdio app-server 查询 Codex 线程状态
    - ⚠️thread/list 固定启用 useStateDbOnly；不会扫描 JSONL rollouts
    - 🚩只发送 initialize 与 thread/list，不调用 resume/read/写入方法
    '''

    def __init__(self, executable: str, timeout_seconds: float) -> None:
        self._timeout_seconds = timeout_seconds
        try:
            self._process = subprocess.Popen(
                [executable, 'app-server', '--stdio'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding='utf-8',
                bufsize=1,
            )
        except OSError as exc:
            raise SourceReadError('codex', 'start_failed') from exc
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        self._stdin = self._process.stdin
        self._responses: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._next_request_id = 0
        self._reader = threading.Thread(target=self._read_responses, daemon=True)
        self._reader.start()

    def _read_responses(self) -> None:
        '''只把带 request id 的 JSON-RPC 响应交给调用者
        - ⚠️服务端通知可能含线程元数据；通知被即时丢弃，不保存或转发
        '''
        assert self._process.stdout is not None
        try:
            for line in self._process.stdout:
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    self._responses.put(None)
                    return
                if isinstance(message, dict) and 'id' in message:
                    self._responses.put(message)
        finally:
            self._responses.put(None)

    def request(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        '''发送一条只读 JSON-RPC 请求并等待相同 id 的响应'''
        self._next_request_id += 1
        request_id = self._next_request_id
        request = {'id': request_id, 'method': method, 'params': dict(params)}
        try:
            self._stdin.write(json.dumps(request, separators=(',', ':')) + '\n')
            self._stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise SourceReadError('codex', 'request_failed') from exc

        deadline = time.monotonic() + self._timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SourceReadError('codex', 'timeout')
            try:
                message = self._responses.get(timeout=remaining)
            except queue.Empty as exc:
                raise SourceReadError('codex', 'timeout') from exc
            if message is None:
                raise SourceReadError('codex', 'response_stream_closed')
            if message.get('id') != request_id:
                continue
            error = message.get('error')
            if isinstance(error, dict):
                raise SourceReadError('codex', 'rpc_error')
            result = message.get('result')
            if not isinstance(result, dict):
                raise SourceReadError('codex', 'invalid_response')
            return result

    def notify(self, method: str, params: Mapping[str, Any]) -> None:
        '''发送 JSON-RPC 通知，不等待或记录通知响应'''
        try:
            self._stdin.write(
                json.dumps({'method': method, 'params': dict(params)}, separators=(',', ':'))
                + '\n'
            )
            self._stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise SourceReadError('codex', 'notification_failed') from exc

    def close(self) -> None:
        '''终止本次查询专用的 app-server 子进程'''
        try:
            self._stdin.close()
        except OSError:
            pass
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)


def _timestamp(value: datetime) -> str:
    '''把带时区时间转换为 RFC 3339 UTC 字符串'''
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timestamp must include a timezone')
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _add_source_freshness(
    projection: dict[str, Any],
    source_observed_at: Mapping[str, datetime],
    *,
    now: datetime,
) -> None:
    '''把每个来源最近成功读取年龄和新鲜度状态加到呈现投影
    - 📌年龄基于宿主收到快照的本机时间，不冒充来源端的精确生成时间
    - 🚩单源断开时保留上次成功读取时间，并单独报告断开状态
    '''
    ages: dict[str, int | None] = {}
    freshness: dict[str, str] = {}
    source_health = projection.get('source_health', {})
    for source_id in LIVE_SOURCE_LABELS:
        observed_at = source_observed_at.get(source_id)
        if observed_at is None:
            ages[source_id] = None
            freshness[source_id] = (
                'unavailable'
                if source_health.get(source_id) == 'unavailable'
                else 'unknown'
            )
            continue

        age_seconds = max(0, int((now - observed_at).total_seconds()))
        ages[source_id] = age_seconds
        if source_health.get(source_id) == 'disconnected':
            freshness[source_id] = 'disconnected'
        elif age_seconds > SOURCE_SNAPSHOT_TTL_SECONDS:
            freshness[source_id] = 'stale'
        else:
            freshness[source_id] = 'fresh'

    projection['source_age_seconds'] = ages
    projection['source_freshness'] = freshness


def _opaque_id(source_id: str, raw_id: str) -> str:
    '''建立稳定的不可逆展示身份，不返回来源原始会话标识'''
    digest = hashlib.sha256(f'{source_id}\0{raw_id}'.encode('utf-8')).hexdigest()[:24]
    return f'sha256-{digest}'


def _activity_record(
    *,
    source_id: str,
    raw_id: str,
    parent_raw_id: str | None,
    status: str,
    normalized_status: str,
    authority: str,
    sequence: int,
    observed_at: datetime,
) -> dict[str, Any]:
    '''构造不包含会话正文或路径的 activity draft 记录'''
    source_type_labels = {
        'codex': 'Codex',
        'codex-app': 'Codex App',
        'claude-code': 'Claude Code',
    }
    provider_ids = {
        'codex': 'codex-cli',
        'codex-app': 'codex-app-connector',
        'claude-code': 'claude-code-cli',
    }
    source_type_label = source_type_labels[source_id]
    identity = _opaque_id(source_id, raw_id)
    display_suffix = identity[-6:]
    expires_at = observed_at + timedelta(seconds=SOURCE_SNAPSHOT_TTL_SECONDS)
    return {
        'kind': 'wincraft.activity.draft',
        'schema_version': 'draft-2026-10-29',
        'source_type': source_id,
        'device_id': 'local-device',
        'provider_id': provider_ids[source_id],
        'mapping_version': LIVE_MAPPING_VERSION,
        'source_instance_id': f'{source_id}-local',
        'session_id': identity,
        'parent_session_id': _opaque_id(source_id, parent_raw_id) if parent_raw_id else None,
        'task_id': None,
        'display_name': f'{source_type_label} · {display_suffix}',
        'model_name': '',
        'source_status': status,
        'normalized_status': normalized_status,
        'observed_at': _timestamp(observed_at),
        'expires_at': _timestamp(expires_at),
        'source_sequence': sequence,
        'freshness': 'fresh',
        'authority': authority,
        'summary': '',
        'control_capabilities': [],
        'provenance': 'official-cli',
    }


def normalize_claude_agents(
    payload: object,
    *,
    observed_at: datetime,
    sequence: int,
) -> tuple[list[dict[str, Any]], str]:
    '''规范化 Claude Code agents --json 输出
    - 📌只读取 id 与 state；忽略 cwd、sessionId、name 和其余会话字段
    - 🚩返回的状态是 online 或 partial；未知 state 不会原样透传
    '''
    if not isinstance(payload, list):
        raise SourceReadError('claude-code', 'invalid_payload')
    records: list[dict[str, Any]] = []
    identities: set[str] = set()
    partial = False
    state_map = {
        'active': ('active', 'running', 'source'),
        'blocked': ('blocked', 'blocked', 'source'),
        'idle': ('idle', 'idle', 'source'),
    }
    for source_order, item in enumerate(payload):
        if not isinstance(item, Mapping):
            partial = True
            continue
        raw_id = item.get('id')
        if not isinstance(raw_id, str) or not raw_id:
            partial = True
            continue
        if raw_id in identities:
            raise SourceReadError('claude-code', 'duplicate_session_identity')
        identities.add(raw_id)
        status_entry = state_map.get(item.get('state'))
        if status_entry is None:
            status_entry = ('unknown', 'unknown', 'unknown')
            partial = True
        source_status, normalized_status, authority = status_entry
        records.append(
            _activity_record(
                source_id='claude-code',
                raw_id=raw_id,
                parent_raw_id=None,
                status=source_status,
                normalized_status=normalized_status,
                authority=authority,
                sequence=sequence * SOURCE_SEQUENCE_STRIDE + source_order,
                observed_at=observed_at,
            )
        )
    return records, 'partial' if partial else 'online'


def _codex_status(thread: Mapping[str, Any]) -> tuple[str, str, str, bool]:
    '''把 app-server ThreadStatus 映射到受限活动状态和显示身份'''
    state = thread.get('status')
    if not isinstance(state, Mapping):
        return 'unknown', 'unknown', 'unknown', False
    state_type = state.get('type')
    if state_type not in KNOWN_CODEX_STATUS_TYPES:
        return 'unknown', 'unknown', 'unknown', False
    if state_type == 'active':
        flags = state.get('activeFlags', [])
        if not isinstance(flags, list):
            return 'unknown', 'unknown', 'unknown', False
        if 'waitingOnApproval' in flags:
            return 'waiting_approval', 'waiting_approval', 'adapter_mapping', True
        if 'waitingOnUserInput' in flags:
            return 'waiting_input', 'waiting_input', 'adapter_mapping', True
        return 'active', 'running', 'adapter_mapping', True
    mapping = {
        'idle': ('idle', 'idle', 'source'),
        'notLoaded': ('notLoaded', 'unknown', 'unknown'),
        'systemError': ('systemError', 'failed', 'adapter_mapping'),
    }
    return (*mapping[state_type], True)


def normalize_codex_threads(
    payload: object,
    *,
    observed_at: datetime,
    sequence: int,
) -> tuple[list[dict[str, Any]], str]:
    '''规范化 Codex app-server thread/list 响应
    - 📌只读取 id、parentThreadId 与 status；忽略 name、preview、cwd、path 和 turns
    - 🚩thread/list 请求必须由调用者使用 useStateDbOnly，避免扫描 rollout JSONL
    '''
    if not isinstance(payload, Mapping) or not isinstance(payload.get('data'), list):
        raise SourceReadError('codex', 'invalid_payload')
    raw_items = payload['data']
    items = [item for item in raw_items if isinstance(item, Mapping)]
    if len(items) != len(raw_items):
        raise SourceReadError('codex', 'invalid_thread_item')
    truncated = len(items) > MAX_ACTIVITIES
    items = items[:MAX_ACTIVITIES]
    raw_ids = {item.get('id') for item in items if isinstance(item.get('id'), str)}
    records: list[dict[str, Any]] = []
    partial = truncated
    seen: set[str] = set()
    for source_order, item in enumerate(items):
        raw_id = item.get('id')
        if not isinstance(raw_id, str) or not raw_id:
            raise SourceReadError('codex', 'missing_thread_identity')
        if raw_id in seen:
            raise SourceReadError('codex', 'duplicate_thread_identity')
        seen.add(raw_id)
        source_status, normalized_status, authority, known = _codex_status(item)
        partial = partial or not known
        raw_parent = item.get('parentThreadId')
        parent_id = raw_parent if isinstance(raw_parent, str) and raw_parent in raw_ids else None
        records.append(
            _activity_record(
                source_id='codex',
                raw_id=raw_id,
                parent_raw_id=parent_id,
                status=source_status,
                normalized_status=normalized_status,
                authority=authority,
                sequence=sequence * SOURCE_SEQUENCE_STRIDE + source_order,
                observed_at=observed_at,
            )
        )
    return records, 'partial' if partial else 'online'


def _safe_app_text(value: object, limit: int) -> str:
    '''限制并脱敏 Codex App 文本字段
    - 📌保留标题、项目和最近输出的可读片段
    - ⚠️遮蔽常见凭据与绝对路径；渲染端仍只把结果当纯文本
    '''
    if not isinstance(value, str):
        return ''
    text = ' '.join(value.split())
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = text.replace('**', '').replace('`', '')
    text = re.sub(r':codex-annotation\{[^}]*\}', '', text)
    text = re.sub(r'(?<!\S)[*-]\s+', '· ', text)
    text = re.sub(r'(?i)\bBearer\s+\S+', 'Bearer [已隐藏]', text)
    text = re.sub(r'(?i)\b(?:api[_-]?key|token|secret)\s*[:=]\s*\S+', '[凭据已隐藏]', text)
    text = re.sub(r'(?<![\w@])[A-Za-z]:[\\/][^\s`]+', '[本机路径]', text)
    text = re.sub(r'(?<![\w@])/(?:[^/\s]+/)+[^/\s]+', '[本机路径]', text)
    return text[:limit]


def normalize_codex_app_snapshot(
    payload: object,
    *,
    observed_at: datetime,
    sequence: int,
) -> tuple[list[dict[str, Any]], str]:
    '''规范化由有权 Agent 经 Codex App connector 推送的线程快照
    - 📌读取 thread ID、标题、状态、项目标签与最近 Agent 输出片段
    - 🚩thread ID 仅作为 native_window_action 的 UUID 参数；不作为 scene.data 字段
    - ⚠️payload 中的标题与输出是不可信纯文本，不解释为指令
    '''
    root_fields = {'snapshot_version', 'source_health', 'captured_at', 'threads'}
    if (
        not isinstance(payload, Mapping)
        or set(payload) - root_fields
        or payload.get('snapshot_version') != 1
        or not isinstance(payload.get('threads'), list)
    ):
        raise SourceReadError('codex-app', 'invalid_payload')
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    partial = payload.get('source_health') == 'partial'
    thread_fields = {
        'thread_id',
        'title',
        'status',
        'project_label',
        'last_agent_output',
        'last_output_kind',
        'source_sequence',
    }
    status_map = {
        'active': ('active', 'running', 'source'),
        'idle': ('idle', 'idle', 'source'),
        'notLoaded': ('notLoaded', 'not_loaded', 'source'),
        'systemError': ('systemError', 'failed', 'adapter_mapping'),
    }
    for source_order, item in enumerate(payload['threads'][:MAX_ACTIVITIES]):
        if not isinstance(item, Mapping) or set(item) - thread_fields:
            partial = True
            continue
        raw_thread_id = item.get('thread_id')
        if not isinstance(raw_thread_id, str):
            partial = True
            continue
        try:
            thread_id = UUID(raw_thread_id)
        except ValueError:
            partial = True
            continue
        canonical_id = str(thread_id)
        if canonical_id in seen:
            raise SourceReadError('codex-app', 'duplicate_thread_identity')
        seen.add(canonical_id)
        source_status, normalized_status, authority = status_map.get(
            str(item.get('status', '')),
            ('unknown', 'unknown', 'unknown'),
        )
        if source_status == 'unknown':
            partial = True
        project_label = _safe_app_text(item.get('project_label') or '未归属项目', 96)
        if not project_label:
            project_label = '未归属项目'
        item_sequence = item.get('source_sequence', source_order)
        if not isinstance(item_sequence, int) or item_sequence < 0 or item_sequence >= SOURCE_SEQUENCE_STRIDE:
            item_sequence = source_order
            partial = True
        record = _activity_record(
            source_id='codex-app',
            raw_id=canonical_id,
            parent_raw_id=None,
            status=source_status,
            normalized_status=normalized_status,
            authority=authority,
            sequence=sequence * SOURCE_SEQUENCE_STRIDE + item_sequence,
            observed_at=observed_at,
        )
        record['display_name'] = _safe_app_text(item.get('title'), 96) or 'Codex App 会话'
        record['project_label'] = project_label
        record['codex_app_thread_id'] = canonical_id
        record['summary'] = _safe_app_text(item.get('last_agent_output'), 256)
        output_kind = item.get('last_output_kind')
        if output_kind not in {'agent_message', 'connector_summary', 'unavailable'}:
            output_kind = 'unavailable'
            partial = True
        if not record['summary']:
            output_kind = 'unavailable'
        record['last_output_kind'] = output_kind
        record['provenance'] = 'official-api'
        records.append(record)
    if len(payload['threads']) > MAX_ACTIVITIES:
        partial = True
    return records, 'partial' if partial else 'online'


def read_claude_agents(
    *,
    observed_at: datetime,
    sequence: int,
    timeout_seconds: float = CLI_TIMEOUT_SECONDS,
) -> tuple[list[dict[str, Any]], str]:
    '''通过 Claude Code 官方 agents --json CLI 查询当前会话元数据'''
    executable = shutil.which(CLAUDE_COMMAND)
    if executable is None:
        raise SourceReadError('claude-code', 'cli_not_found')
    try:
        result = subprocess.run(
            [executable, 'agents', '--json'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SourceReadError('claude-code', 'timeout') from exc
    except OSError as exc:
        raise SourceReadError('claude-code', 'process_start_failed') from exc
    if result.returncode != 0:
        raise SourceReadError('claude-code', 'cli_failed')
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SourceReadError('claude-code', 'invalid_json') from exc
    return normalize_claude_agents(payload, observed_at=observed_at, sequence=sequence)


def read_codex_threads(
    *,
    observed_at: datetime,
    sequence: int,
    timeout_seconds: float = CODEX_RPC_TIMEOUT_SECONDS,
) -> tuple[list[dict[str, Any]], str]:
    '''通过 Codex app-server thread/list 读取本机状态数据库
    - 📌固定 useStateDbOnly=true，不扫描 rollout JSONL、不读取会话正文
    - ⚠️Codex app-server 是实验接口，结果范围仅为本机 CLI 状态库
    '''
    executable = shutil.which(CODEX_COMMAND)
    if executable is None:
        raise SourceReadError('codex', 'cli_not_found')
    client: _CodexAppServer | None = None
    try:
        client = _CodexAppServer(executable, timeout_seconds)
        client.request(
            'initialize',
            {
                'clientInfo': {
                    'name': 'wincraft-agent-board',
                    'title': 'WinCraft read-only activity provider',
                    'version': LIVE_MAPPING_VERSION,
                }
            },
        )
        client.notify('initialized', {})
        threads: list[dict[str, Any]] = []
        cursor: str | None = None
        health = 'online'
        for page_number in range(CODEX_MAX_THREAD_PAGES):
            params: dict[str, Any] = {
                'archived': False,
                'limit': CODEX_THREAD_PAGE_LIMIT,
                'useStateDbOnly': True,
            }
            if cursor is not None:
                params['cursor'] = cursor
            page = client.request('thread/list', params)
            data = page.get('data')
            if not isinstance(data, list):
                raise SourceReadError('codex', 'invalid_thread_page')
            threads.extend(item for item in data if isinstance(item, dict))
            cursor = page.get('nextCursor')
            if not isinstance(cursor, str) or not cursor:
                cursor = None
                break
            if page_number + 1 == CODEX_MAX_THREAD_PAGES:
                health = 'partial'
        records, item_health = normalize_codex_threads(
            {'data': threads},
            observed_at=observed_at,
            sequence=sequence,
        )
        if item_health == 'partial':
            health = 'partial'
        return records, health
    except SourceReadError:
        raise
    except Exception as exc:
        raise SourceReadError('codex', 'app_server_failed') from exc
    finally:
        if client is not None:
            client.close()


def _stale_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    '''将上一次成功快照标为断开，不改动其他来源'''
    stale: list[dict[str, Any]] = []
    for source_record in records:
        record = dict(source_record)
        record['freshness'] = 'disconnected'
        record['normalized_status'] = 'stale'
        stale.append(record)
    return stale


def load_live_snapshot(
    previous: LiveSnapshot | None = None,
    *,
    sequence: int = 0,
    now: datetime | None = None,
) -> LiveSnapshot:
    '''独立读取两个本机 CLI 来源并保留 Agent-fed Codex App 快照
    - 📌单源失败只令该来源过期，Codex App 连接状态独立维护
    '''
    observed_at = now or datetime.now(timezone.utc)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError('now must include a timezone')
    observed_at = observed_at.astimezone(timezone.utc)
    readers = {
        'codex': read_codex_threads,
        'claude-code': read_claude_agents,
    }
    previous_records = previous.records_by_source if previous is not None else {}
    previous_health = (
        previous.projection.get('source_health', {}) if previous is not None else {}
    )
    source_observed_at = (
        dict(previous.source_observed_at) if previous is not None else {}
    )
    records_by_source: dict[str, list[dict[str, Any]]] = {'codex-app': []}
    health: dict[str, str] = {'codex-app': 'unavailable'}
    if previous is not None:
        app_records = previous_records.get('codex-app', [])
        app_health = previous_health.get('codex-app', 'unavailable')
        app_observed_at = source_observed_at.get('codex-app')
        if (
            app_observed_at is not None
            and observed_at - app_observed_at <= timedelta(seconds=SOURCE_SNAPSHOT_TTL_SECONDS)
        ):
            records_by_source['codex-app'] = app_records
            health['codex-app'] = app_health
        elif app_records:
            records_by_source['codex-app'] = _stale_records(app_records)
            health['codex-app'] = 'disconnected'
        elif app_health == 'disconnected':
            health['codex-app'] = 'disconnected'
    for source_id, reader in readers.items():
        try:
            records, source_health = reader(observed_at=observed_at, sequence=sequence)
        except SourceReadError:
            records_by_source[source_id] = _stale_records(previous_records.get(source_id, []))
            health[source_id] = 'disconnected'
        else:
            records_by_source[source_id] = records
            health[source_id] = source_health
            source_observed_at[source_id] = observed_at

    records = [record for source_records in records_by_source.values() for record in source_records]
    projection = aggregate_activities(records, now=observed_at)
    projection['source_health'] = health
    projection['source_labels'] = LIVE_SOURCE_LABELS
    projection['data_mode_label'] = '本机 CLI 实时 · Codex App 等待 Agent 接入'
    projection['codex_app_links_enabled'] = bool(
        previous and previous.projection.get('codex_app_links_enabled')
    )
    _add_source_freshness(projection, source_observed_at, now=observed_at)
    return LiveSnapshot(projection, records_by_source, sequence, source_observed_at)


def merge_codex_app_snapshot(
    previous: LiveSnapshot,
    payload: object,
    *,
    sequence: int,
    now: datetime | None = None,
    links_enabled: bool,
) -> LiveSnapshot:
    '''合并来自 Codex App MCP connector 的 Agent-fed 快照
    - 📌本 Provider 不直接调用 Codex App connector；调用方必须提供受限快照
    - 🚩只接受标题、状态、项目名和最近 Agent 输出片段
    '''
    observed_at = now or datetime.now(timezone.utc)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError('now must include a timezone')
    observed_at = observed_at.astimezone(timezone.utc)
    if not isinstance(payload, Mapping):
        raise SourceReadError('codex-app', 'invalid_payload')

    supplied_health = payload.get('source_health', 'online')
    if supplied_health in {'disconnected', 'unavailable'}:
        records = _stale_records(previous.records_by_source.get('codex-app', []))
        health = 'disconnected' if records else 'unavailable'
        observed_source_at = previous.source_observed_at.get('codex-app')
    elif supplied_health in {'online', 'partial'}:
        records, normalized_health = normalize_codex_app_snapshot(
            payload,
            observed_at=observed_at,
            sequence=sequence,
        )
        health = 'partial' if supplied_health == 'partial' or normalized_health == 'partial' else 'online'
        observed_source_at = observed_at
    else:
        raise SourceReadError('codex-app', 'invalid_source_health')

    records_by_source = dict(previous.records_by_source)
    records_by_source['codex-app'] = records
    health_by_source = dict(previous.projection.get('source_health', {}))
    health_by_source['codex-app'] = health
    source_observed_at = dict(previous.source_observed_at)
    if observed_source_at is not None:
        source_observed_at['codex-app'] = observed_source_at

    all_records = [record for source_records in records_by_source.values() for record in source_records]
    projection = aggregate_activities(all_records, now=observed_at)
    projection['source_health'] = health_by_source
    projection['source_labels'] = LIVE_SOURCE_LABELS
    if health in {'online', 'partial'}:
        projection['data_mode_label'] = 'Codex App + CLI 实时只读'
    elif health == 'disconnected':
        projection['data_mode_label'] = '本机 CLI 实时 · Codex App 桥接断开'
    else:
        projection['data_mode_label'] = '本机 CLI 实时 · Codex App 等待 Agent 接入'
    projection['codex_app_links_enabled'] = links_enabled
    _add_source_freshness(projection, source_observed_at, now=observed_at)
    return LiveSnapshot(projection, records_by_source, sequence, source_observed_at)


def summarize_live_snapshot(snapshot: LiveSnapshot) -> dict[str, Any]:
    '''返回可记录的聚合状态，不含任何会话身份或正文
    - 📌仅包含来源健康、来源条数与规范化状态计数
    '''
    source_counts: dict[str, dict[str, int]] = {}
    for source_id, records in snapshot.records_by_source.items():
        counts = Counter(record['normalized_status'] for record in records)
        source_counts[source_id] = dict(sorted(counts.items()))
    return {
        'sequence': snapshot.sequence,
        'source_health': dict(snapshot.projection['source_health']),
        'status_counts': source_counts,
    }
