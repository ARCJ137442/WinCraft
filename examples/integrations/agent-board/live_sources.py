'''只读采集 Codex Desktop 本机状态、Codex CLI 与 Claude Code 的活动状态
- 🎯将官方 CLI 状态转换为受限的 WinCraft activity 投影
- ⚠️只保留每个可见会话最近一条 Agent 文本；不保留提示词、工具输出或完整日志
'''
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import threading
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
CODEX_OUTPUT_READ_TIMEOUT_SECONDS: float = 1.5
'''📜单个 Codex 线程最近 Agent 输出读取等待上限'''
CODEX_OUTPUT_READ_LIMIT: int = 4
'''📜每轮最多读取最近四个 Codex CLI 线程的 Agent 输出'''
CODEX_OUTPUT_CACHE_LIMIT: int = 128
'''📜进程内 Codex 最近输出缓存上限'''
CODEX_APP_LOCAL_STATE_LIMIT: int = 128
'''📜只展示本机 Codex Desktop state DB 的最近会话元数据'''
CODEX_APP_LOCAL_OUTPUT_READ_LIMIT: int = 4
'''📜每次轮询最多读取四个最近 Codex Desktop rollout 尾部'''
CODEX_APP_ROLLOUT_TAIL_BYTES: int = 1024 * 1024
'''📜本机 Codex Desktop 每条 rollout 最多读取的尾部字节数'''
CLAUDE_OUTPUT_TAIL_BYTES: int = 256 * 1024
'''📜每个 Claude 活动会话最多读取的 JSONL 尾部字节数'''
CLAUDE_OUTPUT_READ_LIMIT: int = 24
'''📜每轮最多读取的 Claude 活动会话输出数'''
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
_CODEX_AGENT_OUTPUT_CACHE: OrderedDict[str, tuple[int, str]] = OrderedDict()
'''🔒只在 Provider 进程中缓存已脱敏的 Codex 最近 Agent 文本，不落盘'''
_CODEX_APP_OUTPUT_CACHE: OrderedDict[str, tuple[int, int, str]] = OrderedDict()
'''🔒只在 Provider 进程中缓存已脱敏的 Codex Desktop 最近 Agent 文本，不落盘'''


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
    - 📌records_by_source 保存哈希身份、脱敏名称/项目、受限预览与来源状态
    - 📌sequence 是本 Provider 内递增的采样序号
    '''

    projection: dict[str, Any]
    '''投影给通用 renderer 的状态'''
    records_by_source: dict[str, list[dict[str, Any]]]
    '''只含哈希身份、脱敏标签/短预览与状态；不含完整路径、原始 ID 或完整日志'''
    sequence: int
    '''当前采样序号'''
    source_observed_at: dict[str, datetime]
    '''每个来源最近一次成功快照的来源采集时刻；缺少采集时刻时回退为本机接收时刻'''


def normalize_live_source_selection(enabled_sources: tuple[str, ...] | None) -> tuple[str, ...]:
    '''验证 Provider 本轮获准查询的本机来源集合
    - 🤖未选来源既不启动适配器，也不沿用上一轮数据
    '''
    if enabled_sources is None:
        return tuple(LIVE_SOURCE_LABELS)
    selected = tuple(enabled_sources)
    if (
        not selected
        or len(set(selected)) != len(selected)
        or set(selected) - set(LIVE_SOURCE_LABELS)
    ):
        raise ValueError('enabled_sources must be a non-empty unique subset of known sources')
    return selected


class _CodexAppServer:
    '''通过本地 stdio app-server 查询 Codex 线程状态
    - ⚠️thread/list 固定启用 useStateDbOnly；不会扫描 JSONL rollouts
    - 📌对最近四个线程调用只读 thread/read，仅提取最后的 agentMessage
    - 🚩不调用 resume、turn/start、turn/steer 或其他写入方法
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

    def request(
        self,
        method: str,
        params: Mapping[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        '''发送一条只读 JSON-RPC 请求并等待相同 id 的响应'''
        self._next_request_id += 1
        request_id = self._next_request_id
        request = {'id': request_id, 'method': method, 'params': dict(params)}
        try:
            self._stdin.write(json.dumps(request, separators=(',', ':')) + '\n')
            self._stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise SourceReadError('codex', 'request_failed') from exc

        deadline = time.monotonic() + (
            self._timeout_seconds if timeout_seconds is None else timeout_seconds
        )
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


def _codex_app_capture_time(
    payload: Mapping[str, Any],
    received_at: datetime,
) -> datetime:
    '''读取 Codex App 快照采集时刻
    - 🎯防止延迟送达的旧快照被标成刚刚更新
    - 📌缺少采集时刻的旧格式仍按本机接收时刻处理
    - 🤖【2026-10-29】Agent新增，待人类审阅
    '''
    if 'captured_at' not in payload:  # 兼容早期没有采集时间的桥接快照
        return received_at

    captured_value = payload['captured_at']
    if not isinstance(captured_value, str):
        raise SourceReadError('codex-app', 'invalid_capture_time')
    try:
        captured_at = datetime.fromisoformat(captured_value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise SourceReadError('codex-app', 'invalid_capture_time') from exc
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise SourceReadError('codex-app', 'invalid_capture_time')

    captured_at = captured_at.astimezone(timezone.utc)
    if captured_at > received_at:  # 来源时间不能把年龄倒拨到未来
        raise SourceReadError('codex-app', 'capture_time_in_future')
    return captured_at


def _add_source_freshness(
    projection: dict[str, Any],
    source_observed_at: Mapping[str, datetime],
    *,
    now: datetime,
) -> None:
    '''把每个来源最近成功读取年龄和新鲜度状态加到呈现投影
    - 📌Codex App优先使用授权Agent捕获快照的时刻，旧格式回退到本机接收时刻
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
        elif age_seconds >= SOURCE_SNAPSHOT_TTL_SECONDS:
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
    provider_id: str | None = None,
    source_instance_id: str | None = None,
    provenance: str = 'official-cli',
) -> dict[str, Any]:
    '''构造包含最少会话展示元数据的 activity draft 记录'''
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
        'provider_id': provider_id or provider_ids[source_id],
        'mapping_version': LIVE_MAPPING_VERSION,
        'source_instance_id': source_instance_id or f'{source_id}-local',
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
        'project_label': '',
        'last_output_kind': 'unavailable',
        'control_capabilities': [],
        'provenance': provenance,
    }


def normalize_claude_agents(
    payload: object,
    *,
    observed_at: datetime,
    sequence: int,
    latest_outputs: Mapping[str, str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    '''规范化 Claude Code agents --json 输出
    - 📌读取 id、state、name 与 cwd 的项目目录名
    - 📌只接受由 sessionId 匹配到的本地 JSONL 尾部 Agent 文本
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
        record = _activity_record(
            source_id='claude-code',
            raw_id=raw_id,
            parent_raw_id=None,
            status=source_status,
            normalized_status=normalized_status,
            authority=authority,
            sequence=sequence * SOURCE_SEQUENCE_STRIDE + source_order,
            observed_at=observed_at,
        )
        record['display_name'] = _safe_app_text(item.get('name'), 96) or record['display_name']
        record['project_label'] = _project_label_from_cwd(item.get('cwd'))
        raw_session_id = item.get('sessionId')
        output = (
            latest_outputs.get(raw_session_id, '')
            if isinstance(raw_session_id, str) and latest_outputs is not None
            else ''
        )
        record['summary'] = _safe_app_text(output, 256)
        record['last_output_kind'] = 'agent_message' if record['summary'] else 'unavailable'
        records.append(record)
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
    agent_outputs: Mapping[str, str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    '''规范化 Codex app-server thread/list 响应
    - 📌读取 id、parentThreadId、status、name 与 cwd；忽略 preview
    - 📌agent_outputs 仅接收 thread/read 中 type=agentMessage 的脱敏文本
    - 🚩thread/list preview 通常是最初的用户消息，不作为 Agent 输出或卡片摘要呈现
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
        record = _activity_record(
            source_id='codex',
            raw_id=raw_id,
            parent_raw_id=parent_id,
            status=source_status,
            normalized_status=normalized_status,
            authority=authority,
            sequence=sequence * SOURCE_SEQUENCE_STRIDE + source_order,
            observed_at=observed_at,
        )
        record['display_name'] = _safe_app_text(item.get('name'), 96) or record['display_name']
        record['project_label'] = _project_label_from_cwd(item.get('cwd'))
        agent_output = (
            agent_outputs.get(raw_id, '')
            if agent_outputs is not None
            else ''
        )
        record['summary'] = _safe_app_text(agent_output, 256)
        record['last_output_kind'] = 'agent_message' if record['summary'] else 'unavailable'
        records.append(record)
    return records, 'partial' if partial else 'online'


def _safe_app_text(value: object, limit: int) -> str:
    '''限制并脱敏来源提供的会话展示文本
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


def _codex_last_agent_output(response: Mapping[str, Any]) -> str:
    '''Extract only the final assistant-authored item from a read-only thread response'''
    thread = response.get('thread')
    turns = thread.get('turns') if isinstance(thread, Mapping) else None
    if not isinstance(turns, list):
        return ''
    latest_agent = ''
    for turn in turns:
        if not isinstance(turn, Mapping) or not isinstance(turn.get('items'), list):
            continue
        for item in turn['items']:
            if not isinstance(item, Mapping) or item.get('type') != 'agentMessage':
                continue
            text = _safe_app_text(item.get('text'), 256)
            if not text:
                continue
            latest_agent = text
    return latest_agent


def _read_codex_latest_outputs(
    client: _CodexAppServer,
    threads: list[dict[str, Any]],
) -> tuple[dict[str, str], bool]:
    '''Read at most four recent threads; cache only the sanitized last agent message in memory'''
    candidates = [
        item for item in threads
        if isinstance(item.get('id'), str) and item.get('id')
    ]
    candidates.sort(
        key=lambda item: item.get('updatedAt') if isinstance(item.get('updatedAt'), int) else 0,
        reverse=True,
    )
    outputs: dict[str, str] = {}
    partial = False
    for item in candidates[:CODEX_OUTPUT_READ_LIMIT]:
        thread_id = item['id']
        updated_at = item.get('updatedAt')
        cached = _CODEX_AGENT_OUTPUT_CACHE.get(thread_id)
        if isinstance(updated_at, int) and cached is not None and cached[0] == updated_at:
            _CODEX_AGENT_OUTPUT_CACHE.move_to_end(thread_id)
            if cached[1]:
                outputs[thread_id] = cached[1]
            continue
        try:
            response = client.request(
                'thread/read',
                {'threadId': thread_id, 'includeTurns': True},
                timeout_seconds=CODEX_OUTPUT_READ_TIMEOUT_SECONDS,
            )
        except SourceReadError:
            partial = True
            continue
        output = _codex_last_agent_output(response)
        if isinstance(updated_at, int):
            _CODEX_AGENT_OUTPUT_CACHE[thread_id] = (updated_at, output)
            _CODEX_AGENT_OUTPUT_CACHE.move_to_end(thread_id)
            while len(_CODEX_AGENT_OUTPUT_CACHE) > CODEX_OUTPUT_CACHE_LIMIT:
                _CODEX_AGENT_OUTPUT_CACHE.popitem(last=False)
        if output:
            outputs[thread_id] = output
    return outputs, partial


def _claude_projects_directory(config_dir: Path | None = None) -> Path:
    if config_dir is not None:
        root = config_dir
    else:
        configured = os.environ.get('CLAUDE_CONFIG_DIR')
        root = Path(configured) if configured else Path.home() / '.claude'
    return root / 'projects'


def _read_claude_last_agent_output(
    session_id: str,
    *,
    projects_dir: Path | None = None,
    max_bytes: int = CLAUDE_OUTPUT_TAIL_BYTES,
) -> str:
    '''Read a bounded JSONL tail for one explicitly listed session and retain its last assistant text'''
    if (
        not session_id
        or len(session_id) > 128
        or session_id in {'.', '..'}
        or '/' in session_id
        or '\\' in session_id
    ):
        return ''
    root = projects_dir or _claude_projects_directory()
    try:
        matches = [
            project / f'{session_id}.jsonl'
            for project in root.iterdir()
            if project.is_dir() and (project / f'{session_id}.jsonl').is_file()
        ]
    except OSError:
        return ''
    if len(matches) != 1:
        return ''
    try:
        with matches[0].open('rb') as stream:
            stream.seek(0, 2)
            size = stream.tell()
            offset = max(0, size - max_bytes)
            stream.seek(offset)
            tail = stream.read(max_bytes)
    except OSError:
        return ''
    lines = tail.splitlines()
    if offset:
        lines = lines[1:]
    for line in reversed(lines):
        try:
            item = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(item, Mapping) or item.get('type') != 'assistant':
            continue
        message = item.get('message')
        content = message.get('content') if isinstance(message, Mapping) else None
        if not isinstance(content, list):
            continue
        text = ' '.join(
            block.get('text', '')
            for block in content
            if isinstance(block, Mapping)
            and block.get('type') == 'text'
            and isinstance(block.get('text'), str)
        )
        safe_text = _safe_app_text(text, 256)
        if safe_text:
            return safe_text
    return ''


def _read_claude_latest_outputs(payload: object) -> dict[str, str]:
    '''Read output tails only for active sessions returned by Claude's official status command'''
    if not isinstance(payload, list):
        return {}
    sessions = [item for item in payload if isinstance(item, Mapping)]
    session_id_counts = Counter(
        item['sessionId']
        for item in sessions
        if isinstance(item.get('sessionId'), str)
    )
    sessions.sort(
        key=lambda item: item.get('startedAt') if isinstance(item.get('startedAt'), (int, float)) else 0,
        reverse=True,
    )
    outputs: dict[str, str] = {}
    for item in sessions[:CLAUDE_OUTPUT_READ_LIMIT]:
        session_id = item.get('sessionId')
        if not isinstance(session_id, str) or session_id_counts[session_id] != 1:
            continue
        output = _read_claude_last_agent_output(session_id)
        if output:
            outputs[session_id] = output
    return outputs


def _codex_root(configured_root: Path | None = None) -> Path:
    if configured_root is not None:
        return configured_root
    configured = os.environ.get('CODEX_HOME')
    return Path(configured) if configured else Path.home() / '.codex'


def _latest_codex_state_database(codex_root: Path) -> Path | None:
    try:
        candidates = [
            path for path in codex_root.iterdir()
            if path.is_file()
            and path.name.startswith('state_')
            and path.suffix.casefold() == '.sqlite'
        ]
    except OSError:
        return None
    def modified_ns(path: Path) -> int:
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return 0

    candidates.sort(key=modified_ns, reverse=True)
    return candidates[0] if candidates else None


def _read_codex_rollout_agent_output(
    rollout_path: object,
    thread_id: str,
    *,
    max_bytes: int = CODEX_APP_ROLLOUT_TAIL_BYTES,
) -> str:
    '''Read one bounded Codex Desktop rollout tail after validating its session_meta identity'''
    if not isinstance(rollout_path, str) or not rollout_path:
        return ''
    normalized_path = rollout_path.removeprefix('\\\\?\\')
    path = Path(normalized_path)
    if (
        not path.is_absolute()
        or path.suffix.casefold() != '.jsonl'
        or not path.name.startswith('rollout-')
        or not any(parent.name.casefold() in {'sessions', 'archived_sessions'} for parent in path.parents)
    ):
        return ''
    try:
        resolved = path.resolve(strict=True)
        file_size = resolved.stat().st_size
        modified_ns = resolved.stat().st_mtime_ns
        if (
            not resolved.is_file()
            or resolved.suffix.casefold() != '.jsonl'
            or not resolved.name.startswith('rollout-')
            or not any(
                parent.name.casefold() in {'sessions', 'archived_sessions'}
                for parent in resolved.parents
            )
        ):
            return ''
    except OSError:
        return ''
    cache_key = f'{thread_id}:{hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()}'
    cached = _CODEX_APP_OUTPUT_CACHE.get(cache_key)
    if cached is not None and cached[:2] == (file_size, modified_ns):
        _CODEX_APP_OUTPUT_CACHE.move_to_end(cache_key)
        return cached[2]

    # The path comes from the read-only Codex state database. Confirm the primary
    # session identity before reading a bounded tail from that local rollout.
    try:
        with resolved.open('rb') as stream:
            header = stream.read(64 * 1024)
            stream.seek(max(0, file_size - max_bytes))
            offset = max(0, file_size - max_bytes)
            tail = stream.read(max_bytes)
    except OSError:
        return ''
    identity_matches = False
    for line in header.splitlines():
        if b'"session_meta"' not in line:
            continue
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        payload = entry.get('payload') if isinstance(entry, Mapping) else None
        if isinstance(entry, Mapping) and entry.get('type') == 'session_meta' and isinstance(payload, Mapping):
            try:
                identity_matches = str(UUID(str(payload.get('id')))) == thread_id
            except ValueError:
                identity_matches = False
            if identity_matches:
                break
    if not identity_matches:
        return ''

    lines = tail.splitlines()
    if offset:
        lines = lines[1:]
    output = ''
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(entry, Mapping) or entry.get('type') != 'event_msg':
            continue
        payload = entry.get('payload')
        if not isinstance(payload, Mapping):
            continue
        event_type = payload.get('type')
        candidate = (
            payload.get('message') if event_type == 'agent_message'
            else payload.get('last_agent_message') if event_type == 'task_complete'
            else None
        )
        if isinstance(candidate, str):
            output = _safe_app_text(candidate, 256)
            if output:
                break

    _CODEX_APP_OUTPUT_CACHE[cache_key] = (file_size, modified_ns, output)
    _CODEX_APP_OUTPUT_CACHE.move_to_end(cache_key)
    while len(_CODEX_APP_OUTPUT_CACHE) > 64:
        _CODEX_APP_OUTPUT_CACHE.popitem(last=False)
    return output


def read_codex_app_local_threads(
    *,
    observed_at: datetime,
    sequence: int,
    codex_root: Path | None = None,
) -> tuple[list[dict[str, Any]], str]:
    '''Read exact Codex Desktop-originator rows from the local SQLite state database, without writing
    - 📌保留标题/项目；本地 state DB 不含权威运行状态，因此 status 固定为 unknown
    - 📌仅对最近四个 rollout 验证 session_meta UUID 后读取 bounded Agent message 尾部
    - 🚩不读取 state DB preview，因为它通常是最初的用户消息
    '''
    root = _codex_root(codex_root)
    database_path = _latest_codex_state_database(root)
    if database_path is None:
        return [], 'unavailable'
    connection: sqlite3.Connection | None = None
    try:
        database_uri = database_path.resolve().as_uri() + '?mode=ro'
        connection = sqlite3.connect(database_uri, uri=True, timeout=0.25)
        connection.execute('PRAGMA query_only = ON')
        columns = {
            row[1]
            for row in connection.execute('PRAGMA table_info(threads)').fetchall()
        }
        if not {'id', 'title', 'cwd', 'updated_at_ms', 'originator'}.issubset(columns):
            return [], 'unavailable'
        selected = ['id', 'title', 'cwd', 'updated_at_ms', 'originator']
        for optional in ('name', 'rollout_path', 'archived'):
            if optional in columns:
                selected.append(optional)
        filters = ['LOWER(TRIM(originator)) = ?']
        if 'archived' in columns:
            filters.append('COALESCE(archived, 0) = 0')
        query = (
            f"SELECT {', '.join(selected)} FROM threads "
            f"WHERE {' AND '.join(filters)} ORDER BY updated_at_ms DESC LIMIT ?"
        )
        rows = connection.execute(query, ('codex desktop', CODEX_APP_LOCAL_STATE_LIMIT)).fetchall()
    except (OSError, sqlite3.Error):
        return [], 'unavailable'
    finally:
        if connection is not None:
            connection.close()

    records: list[dict[str, Any]] = []
    partial = False
    for source_order, row in enumerate(rows):
        item = dict(zip(selected, row))
        raw_id = item.get('id')
        if not isinstance(raw_id, str):
            partial = True
            continue
        try:
            thread_id = str(UUID(raw_id))
        except ValueError:
            partial = True
            continue
        record = _activity_record(
            source_id='codex-app',
            raw_id=thread_id,
            parent_raw_id=None,
            status='unknown',
            normalized_status='unknown',
            authority='unknown',
            sequence=sequence * SOURCE_SEQUENCE_STRIDE + source_order,
            observed_at=observed_at,
            provider_id='codex-app-local-state',
            source_instance_id='codex-app-local-state',
            provenance='local-state-db',
        )
        record['display_name'] = (
            _safe_app_text(item.get('name'), 96)
            or _safe_app_text(item.get('title'), 96)
            or 'Codex App 会话'
        )
        record['project_label'] = _project_label_from_cwd(item.get('cwd')) or '未归属项目'
        record['codex_app_thread_id'] = thread_id
        summary = (
            _read_codex_rollout_agent_output(item.get('rollout_path'), thread_id)
            if source_order < CODEX_APP_LOCAL_OUTPUT_READ_LIMIT
            else ''
        )
        record['summary'] = summary
        record['last_output_kind'] = 'agent_message' if summary else 'unavailable'
        records.append(record)
    if len(rows) >= CODEX_APP_LOCAL_STATE_LIMIT:
        partial = True
    return records, 'partial' if partial else 'local_state'


def _project_label_from_cwd(value: object) -> str:
    '''只从工作目录提取项目末级名称，不把绝对路径带入 activity 数据'''
    if not isinstance(value, str) or not value.strip():
        return ''
    parts = [part for part in value.replace('\\', '/').split('/') if part]
    if len(parts) < 3 or parts[-2].casefold() in {'users', 'home'}:
        return ''
    return _safe_app_text(parts[-1], 96)


def normalize_codex_app_snapshot(
    payload: object,
    *,
    observed_at: datetime,
    sequence: int,
) -> tuple[list[dict[str, Any]], str]:
    '''规范化由有权 Agent 经 Codex App connector 推送的线程快照
    - 📌读取 thread ID、标题、状态、项目标签与最近 Agent 输出片段
    - 📌captured_at控制来源年龄与会话TTL，缺少字段时回退到接收时刻
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
    captured_at = _codex_app_capture_time(payload, observed_at)
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
            observed_at=captured_at,
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
    latest_outputs = _read_claude_latest_outputs(payload)
    return normalize_claude_agents(
        payload,
        observed_at=observed_at,
        sequence=sequence,
        latest_outputs=latest_outputs,
    )


def read_codex_threads(
    *,
    observed_at: datetime,
    sequence: int,
    timeout_seconds: float = CODEX_RPC_TIMEOUT_SECONDS,
) -> tuple[list[dict[str, Any]], str]:
    '''通过 Codex app-server thread/list 读取本机状态数据库
    - 📌固定 useStateDbOnly=true，不扫描 rollout JSONL
    - 📌仅对最近四个线程调用 thread/read，提取并缓存最后一条 agentMessage
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
        agent_outputs, output_read_partial = _read_codex_latest_outputs(client, threads)
        records, item_health = normalize_codex_threads(
            {'data': threads},
            observed_at=observed_at,
            sequence=sequence,
            agent_outputs=agent_outputs,
        )
        if item_health == 'partial' or output_read_partial:
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


def _codex_app_local_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if record.get('provider_id') == 'codex-app-local-state']


def _codex_app_connector_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if record.get('provider_id') != 'codex-app-local-state']


def _merge_codex_app_records(
    local_records: list[dict[str, Any]],
    connector_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    '''Prefer connector fields for matching ids while keeping locally discovered Desktop threads'''
    local_by_id = {
        record['codex_app_thread_id']: record
        for record in local_records
        if isinstance(record.get('codex_app_thread_id'), str)
    }
    merged: list[dict[str, Any]] = []
    connector_ids: set[str] = set()
    for connector in connector_records:
        thread_id = connector.get('codex_app_thread_id')
        if not isinstance(thread_id, str):
            continue
        connector_ids.add(thread_id)
        combined = dict(connector)
        local = local_by_id.get(thread_id)
        if local is not None:
            if (
                combined.get('display_name') == 'Codex App 会话'
                and local.get('display_name')
            ):
                combined['display_name'] = local['display_name']
            if (
                combined.get('project_label') == '未归属项目'
                and local.get('project_label')
            ):
                combined['project_label'] = local['project_label']
            if (
                not combined.get('summary')
                and local.get('last_output_kind') == 'agent_message'
                and local.get('summary')
            ):
                combined['summary'] = local['summary']
                combined['last_output_kind'] = 'agent_message'
                combined['provenance'] = 'connector+local-state'
        merged.append(combined)
    merged.extend(
        record for record in local_records
        if record.get('codex_app_thread_id') not in connector_ids
    )
    return merged


def load_live_snapshot(
    previous: LiveSnapshot | None = None,
    *,
    sequence: int = 0,
    now: datetime | None = None,
    enabled_sources: tuple[str, ...] | None = None,
) -> LiveSnapshot:
    '''读取显式选择的本机来源并保留 Codex App 的本地 metadata 与 Agent-fed snapshot
    - 📌Codex Desktop state DB 只补本机可重建 metadata；connector snapshot 权威覆盖同一 thread
    - 📌单源失败只令该来源过期；本地 state fallback 不冒充实时运行状态
    - 🤖未选择的来源不读取或复用旧记录，UI以not_requested明确呈现
    '''
    observed_at = now or datetime.now(timezone.utc)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError('now must include a timezone')
    observed_at = observed_at.astimezone(timezone.utc)
    selected_sources = normalize_live_source_selection(enabled_sources)
    selected_source_ids = set(selected_sources)
    all_sources = tuple(LIVE_SOURCE_LABELS)
    readers = {
        'codex': read_codex_threads,
        'claude-code': read_claude_agents,
    }
    previous_records = previous.records_by_source if previous is not None else {}
    previous_health = (
        previous.projection.get('source_health', {}) if previous is not None else {}
    )
    source_observed_at = (
        {
            source_id: observed
            for source_id, observed in previous.source_observed_at.items()
            if source_id in selected_source_ids
        }
        if previous is not None
        else {}
    )
    previous_app_observed_at = (
        source_observed_at.get('codex-app')
    )
    records_by_source: dict[str, list[dict[str, Any]]] = {
        source_id: [] for source_id in all_sources
    }
    health: dict[str, str] = {
        source_id: 'not_requested' for source_id in all_sources
    }
    local_app_records: list[dict[str, Any]] = []
    local_app_health = 'not_requested'
    if 'codex-app' in selected_source_ids:
        try:
            local_app_records, local_app_health = read_codex_app_local_threads(
                observed_at=observed_at,
                sequence=sequence,
            )
        except SourceReadError:
            local_app_records, local_app_health = [], 'unavailable'
        if local_app_health == 'unavailable' and previous is not None:
            previous_local_records = _codex_app_local_records(
                previous_records.get('codex-app', [])
            )
            if previous_local_records:
                local_app_records = _stale_records(previous_local_records)
                local_app_health = 'disconnected'
        records_by_source['codex-app'] = local_app_records
        health['codex-app'] = local_app_health
        if local_app_health in {'local_state', 'partial'}:
            source_observed_at['codex-app'] = observed_at
        if previous is not None:
            app_records = previous_records.get('codex-app', [])
            connector_records = _codex_app_connector_records(app_records)
            app_observed_at = previous_app_observed_at
            if (
                connector_records
                and app_observed_at is not None
                and observed_at - app_observed_at <= timedelta(seconds=SOURCE_SNAPSHOT_TTL_SECONDS)
            ):
                records_by_source['codex-app'] = _merge_codex_app_records(
                    local_app_records,
                    connector_records,
                )
                connector_health = previous_health.get('codex-app', 'partial')
                has_local_only_records = len(records_by_source['codex-app']) > len(connector_records)
                health['codex-app'] = (
                    'partial' if has_local_only_records and connector_health == 'online'
                    else connector_health
                )
                source_observed_at['codex-app'] = max(
                    value for value in (source_observed_at.get('codex-app'), app_observed_at)
                    if value is not None
                )
            elif connector_records:
                stale_connector_records = _stale_records(connector_records)
                records_by_source['codex-app'] = _merge_codex_app_records(
                    local_app_records,
                    stale_connector_records,
                )
                health['codex-app'] = 'local_state' if local_app_health == 'local_state' else 'disconnected'
            elif not local_app_records and previous_health.get('codex-app') == 'disconnected':
                health['codex-app'] = 'disconnected'
    for source_id, reader in readers.items():
        if source_id not in selected_source_ids:
            continue
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
    local_app_present = bool(_codex_app_local_records(records_by_source['codex-app']))
    connector_app_present = bool(_codex_app_connector_records(records_by_source['codex-app']))
    if 'codex-app' not in selected_source_ids:
        projection['data_mode_label'] = '所选 CLI 来源实时只读 · Codex App 本轮未查询'
    elif connector_app_present and local_app_present:
        projection['data_mode_label'] = 'Codex App 桥接 + 本机状态库 + CLI 实时只读'
    elif connector_app_present:
        projection['data_mode_label'] = 'Codex App + CLI 实时只读'
    elif local_app_health == 'local_state' or local_app_present:
        projection['data_mode_label'] = '本机 Codex Desktop 状态库只读 · Agent 状态待桥接'
    else:
        projection['data_mode_label'] = '本机 CLI 实时 · Codex App 等待 Agent 接入'
    projection['codex_app_links_enabled'] = bool(
        'codex-app' in selected_source_ids
        and previous
        and previous.projection.get('codex_app_links_enabled')
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
    - 📌来源年龄和会话TTL服从captured_at，未来或无效时间由该来源失败关闭
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
        previous_app_records = previous.records_by_source.get('codex-app', [])
        local_records = _codex_app_local_records(previous_app_records)
        connector_records = _codex_app_connector_records(previous_app_records)
        stale_connectors = _stale_records(connector_records)
        records = _merge_codex_app_records(local_records, stale_connectors)
        health = 'local_state' if local_records else ('disconnected' if stale_connectors else 'unavailable')
        observed_source_at = previous.source_observed_at.get('codex-app')
    elif supplied_health in {'online', 'partial'}:
        captured_at = _codex_app_capture_time(payload, observed_at)
        connector_records, normalized_health = normalize_codex_app_snapshot(
            payload,
            observed_at=captured_at,
            sequence=sequence,
        )
        local_records = _codex_app_local_records(
            previous.records_by_source.get('codex-app', [])
        )
        records = _merge_codex_app_records(local_records, connector_records)
        local_only_records = len(records) > len(connector_records)
        health = (
            'partial'
            if supplied_health == 'partial'
            or normalized_health == 'partial'
            or local_only_records
            else 'online'
        )
        observed_source_at = captured_at
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
        projection['data_mode_label'] = (
            'Codex App + 本机状态库 + CLI 实时只读'
            if any(record.get('provider_id') == 'codex-app-local-state' for record in records)
            else 'Codex App + CLI 实时只读'
        )
    elif health == 'disconnected':
        projection['data_mode_label'] = '本机 CLI 实时 · Codex App 桥接断开'
    elif health == 'local_state':
        projection['data_mode_label'] = '本机 Codex Desktop 状态库只读 · App Agent 桥接断开'
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
