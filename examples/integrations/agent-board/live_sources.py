'''只读采集 Codex App、Codex CLI 与 Claude Code 的本机活动摘要
- 🎯将本机状态库与会话文件映射为受限的 WinCraft activity 投影
- 📌Codex App/Claude Code 进程在线状态独立于磁盘数据读取
- ⚠️只保留有界、脱敏的最近 Agent 文本；不保留提示词、thinking、工具输出或完整日志
'''
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from collections import Counter, OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from activity_board import MAX_ACTIVITIES, aggregate_activities, identity_key

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
'''📜每轮最多读取的 Claude Code 最近会话输出数'''
CLAUDE_PROJECT_LIMIT: int = 256
'''📜每轮最多扫描的 Claude Code 本地项目目录数'''
CLAUDE_SESSION_FILE_LIMIT: int = 256
'''📜每轮最多读取的 Claude Code 会话文件数'''
CLAUDE_SESSION_HEADER_BYTES: int = 64 * 1024
'''📜验证 Claude Code 会话身份与读取标题时的最大头部字节数'''
CLAUDE_FILE_ACTIVITY_WINDOW_SECONDS: int = 90
'''📜只有进程在线且会话文件近期写入时才将单条会话标为运行中'''
SOURCE_SNAPSHOT_TTL_SECONDS: int = 30
'''📜真实状态快照的有效期；超过后投影为过期'''
SOURCE_SEQUENCE_STRIDE: int = 1024
'''📜为来源列表顺序和快照代次保留不重叠的 sequence 范围'''
LIVE_MAPPING_VERSION: str = '1'
'''📜本地 CLI 状态到 activity draft 的映射版本'''
KNOWN_CLAUDE_STATES = frozenset({'active', 'blocked', 'idle'})
'''📜synthetic/legacy Claude status fixture 的已识别状态集合'''
KNOWN_CODEX_STATUS_TYPES = frozenset({'active', 'idle', 'notLoaded', 'systemError'})
'''📜Codex app-server ThreadStatus 已识别的来源状态集合'''
LIVE_SOURCE_LABELS = {
    'codex': 'Codex CLI · 本机状态库',
    'codex-app': 'Codex App',
    'claude-code': 'Claude Code',
}
'''📜明确区分 Codex CLI、Codex App 和 Claude Code 来源'''
_CODEX_AGENT_OUTPUT_CACHE: OrderedDict[str, tuple[int, str]] = OrderedDict()
'''🔒只在 Provider 进程中缓存已脱敏的 Codex 最近 Agent 文本，不落盘'''
_CODEX_APP_OUTPUT_CACHE: OrderedDict[str, tuple[int, int, str]] = OrderedDict()
'''🔒只在 Provider 进程中缓存已脱敏的 Codex Desktop 最近 Agent 文本，不落盘'''
_CLAUDE_AGENT_OUTPUT_CACHE: OrderedDict[str, tuple[int, int, str]] = OrderedDict()
'''🔒只在 Provider 进程中缓存已脱敏的 Claude Code 最近 Agent 文本，不落盘'''


def _normalized_executable_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ''
    return os.path.normcase(os.path.normpath(os.path.abspath(value)))


def _path_is_within(value: object, root: Path) -> bool:
    path = _normalized_executable_path(value)
    normalized_root = _normalized_executable_path(str(root))
    if not path or not normalized_root:
        return False
    try:
        return os.path.commonpath((path, normalized_root)) == normalized_root
    except (OSError, ValueError):
        return False


def _codex_app_process_running(processes: list[Mapping[str, Any]]) -> bool | None:
    '''Detect the Codex Desktop child process without opening the App or reading its command line'''
    if os.name != 'nt':
        return None
    local_app_data = os.environ.get('LOCALAPPDATA')
    codex_bin_root = (
        Path(local_app_data) / 'OpenAI' / 'Codex' / 'bin'
        if local_app_data
        else Path.home() / 'AppData' / 'Local' / 'OpenAI' / 'Codex' / 'bin'
    )
    by_pid = {
        process.get('pid'): process
        for process in processes
        if isinstance(process.get('pid'), int)
    }
    uncertain = False
    for process in processes:
        name = str(process.get('name') or '').casefold()
        if name not in {'codex.exe', 'codex'}:
            continue
        executable = process.get('exe')
        if not executable:
            uncertain = True
            continue
        if not _path_is_within(str(executable), codex_bin_root):
            continue
        parent_id = process.get('ppid')
        for _ in range(8):
            parent = by_pid.get(parent_id)
            if parent is None:
                uncertain = True
                break
            if str(parent.get('name') or '').casefold() in {'chatgpt.exe', 'openai.codex.exe'}:
                return True
            parent_id = parent.get('ppid')
    return None if uncertain else False


def _claude_code_executable_paths() -> set[str]:
    '''Resolve known Claude Code launcher targets without launching a CLI process'''
    candidates: set[str] = set()
    command = shutil.which(CLAUDE_COMMAND)
    if command:
        launcher = Path(command)
        if launcher.suffix.casefold() in {'.ps1', '.cmd', '.bat'}:
            candidates.add(_normalized_executable_path(str(
                launcher.parent / 'node_modules' / '@anthropic-ai' / 'claude-code' / 'bin' / 'claude.exe'
            )))
        else:
            candidates.add(_normalized_executable_path(str(launcher.resolve(strict=False))))
    app_data = os.environ.get('APPDATA')
    if app_data:
        candidates.add(_normalized_executable_path(str(
            Path(app_data) / 'npm' / 'node_modules' / '@anthropic-ai' / 'claude-code' / 'bin' / 'claude.exe'
        )))
    return {candidate for candidate in candidates if candidate}


def _claude_code_process_running(processes: list[Mapping[str, Any]]) -> bool | None:
    '''Detect the installed Claude Code executable by image path only'''
    expected_paths = _claude_code_executable_paths()
    uncertain = False
    for process in processes:
        name = str(process.get('name') or '').casefold()
        if name not in {'claude.exe', 'claude-code.exe', 'claude'}:
            continue
        executable = process.get('exe')
        if not executable:
            uncertain = True
            continue
        if _normalized_executable_path(str(executable)) in expected_paths:
            return True
    return None if uncertain else False


def _windows_process_image_path(pid: int) -> str | None:
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


def _windows_process_snapshot() -> list[dict[str, Any]]:
    '''Enumerate process names/parent IDs once; query image paths only for Codex/Claude candidates'''
    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ('dwSize', wintypes.DWORD),
            ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD),
            ('th32DefaultHeapID', ctypes.c_size_t),
            ('th32ModuleID', wintypes.DWORD),
            ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD),
            ('pcPriClassBase', wintypes.LONG),
            ('dwFlags', wintypes.DWORD),
            ('szExeFile', wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if not handle or handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(ProcessEntry32W)
        has_entry = kernel32.Process32FirstW(handle, ctypes.byref(entry))
        processes: list[dict[str, Any]] = []
        while has_entry:
            process = {
                'pid': int(entry.th32ProcessID),
                'ppid': int(entry.th32ParentProcessID),
                'name': entry.szExeFile,
                'exe': None,
            }
            if str(process['name']).casefold() in {
                'codex.exe', 'codex', 'claude.exe', 'claude-code.exe', 'claude'
            }:
                process['exe'] = _windows_process_image_path(process['pid'])
            processes.append(process)
            entry.dwSize = ctypes.sizeof(ProcessEntry32W)
            has_entry = kernel32.Process32NextW(handle, ctypes.byref(entry))
        return processes
    finally:
        kernel32.CloseHandle(handle)


def _linux_process_snapshot() -> list[dict[str, Any]]:
    '''Read /proc metadata without spawning a process or reading command lines'''
    processes: list[dict[str, Any]] = []
    proc_root = Path('/proc')
    for path in proc_root.iterdir():
        if not path.name.isdigit():
            continue
        try:
            stat_text = (path / 'stat').read_text(encoding='utf-8')
            close = stat_text.rfind(')')
            fields = stat_text[close + 2:].split()
            name = (path / 'comm').read_text(encoding='utf-8').strip()
            parent_id = int(fields[1])
            process_id = int(path.name)
        except (OSError, ValueError, IndexError):
            continue
        executable = None
        if name.casefold() in {'claude', 'claude-code'}:
            try:
                executable = os.readlink(path / 'exe')
            except OSError:
                pass
        processes.append({'pid': process_id, 'ppid': parent_id, 'name': name, 'exe': executable})
    return processes


def _local_process_snapshot() -> list[dict[str, Any]] | None:
    '''Use native process metadata; unsupported platforms yield unknown instead of false offline'''
    try:
        if os.name == 'nt':
            return _windows_process_snapshot()
        if sys.platform.startswith('linux'):
            return _linux_process_snapshot()
    except OSError:
        return None
    return None


def _local_process_states() -> dict[str, bool | None]:
    '''Observe only process metadata; never launch a Harness or retain command lines'''
    processes = _local_process_snapshot()
    if processes is None:
        return {'codex-app': None, 'claude-code': None}
    return {
        'codex-app': _codex_app_process_running(processes),
        'claude-code': _claude_code_process_running(processes),
    }


def _process_health(running: bool | None) -> str:
    if running is True:
        return 'online'
    if running is False:
        return 'offline'
    return 'unknown'


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
    source_data_health = projection.get('source_data_health', {})
    for source_id in LIVE_SOURCE_LABELS:
        observed_at = source_observed_at.get(source_id)
        if observed_at is None:
            ages[source_id] = None
            freshness[source_id] = (
                'unavailable'
                if (
                    source_health.get(source_id) == 'unavailable'
                    or source_data_health.get(source_id) == 'unavailable'
                )
                else 'unknown'
            )
            continue

        age_seconds = max(0, int((now - observed_at).total_seconds()))
        ages[source_id] = age_seconds
        if (
            source_health.get(source_id) == 'disconnected'
            or source_data_health.get(source_id) == 'disconnected'
        ):
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
        'codex-app': 'codex-app-local-state',
        'claude-code': 'claude-code-local-files',
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
    '''规范化合成 Claude Code status fixture，不参与本机进程或文件读取
    - 📌读取 id、state、name 与 cwd 的项目目录名
    - 📌只接受由 sessionId 匹配到的本地 JSONL 尾部 Agent 文本
    - 🚩runtime reader is read_claude_local_sessions
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
    session_path: Path | None = None,
    expected_agent_id: str | None = None,
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
        resolved_root = root.resolve(strict=True)
        if session_path is not None:
            if session_path.is_symlink() or not session_path.is_file():
                return ''
            matches = [session_path]
        else:
            matches = [
                project / f'{session_id}.jsonl'
                for project in resolved_root.iterdir()
                if project.is_dir()
                and not project.is_symlink()
                and (project / f'{session_id}.jsonl').is_file()
                and not (project / f'{session_id}.jsonl').is_symlink()
            ]
    except OSError:
        return ''
    if len(matches) != 1:
        return ''
    try:
        resolved = matches[0].resolve(strict=True)
        if not _path_is_within(str(resolved), resolved_root) or not resolved.is_file():
            return ''
        metadata = resolved.stat()
        cache_key = hashlib.sha256(
            f'{resolved}\0{session_id}\0{expected_agent_id or ""}'.encode('utf-8')
        ).hexdigest()
        cached = _CLAUDE_AGENT_OUTPUT_CACHE.get(cache_key)
        if cached is not None and cached[:2] == (metadata.st_size, metadata.st_mtime_ns):
            _CLAUDE_AGENT_OUTPUT_CACHE.move_to_end(cache_key)
            return cached[2]
        with resolved.open('rb') as stream:
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
        item_session_id = item.get('sessionId') or item.get('session_id')
        if isinstance(item_session_id, str) and item_session_id.casefold() != session_id.casefold():
            continue
        item_agent_id = item.get('agentId')
        if (
            expected_agent_id is not None
            and isinstance(item_agent_id, str)
            and item_agent_id != expected_agent_id
        ):
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
            _CLAUDE_AGENT_OUTPUT_CACHE[cache_key] = (
                metadata.st_size,
                metadata.st_mtime_ns,
                safe_text,
            )
            _CLAUDE_AGENT_OUTPUT_CACHE.move_to_end(cache_key)
            while len(_CLAUDE_AGENT_OUTPUT_CACHE) > 128:
                _CLAUDE_AGENT_OUTPUT_CACHE.popitem(last=False)
            return safe_text
    _CLAUDE_AGENT_OUTPUT_CACHE[cache_key] = (
        metadata.st_size,
        metadata.st_mtime_ns,
        '',
    )
    _CLAUDE_AGENT_OUTPUT_CACHE.move_to_end(cache_key)
    while len(_CLAUDE_AGENT_OUTPUT_CACHE) > 128:
        _CLAUDE_AGENT_OUTPUT_CACHE.popitem(last=False)
    return ''


_CLAUDE_SESSION_METADATA_CACHE: OrderedDict[
    str, tuple[int, int, dict[str, str] | None]
] = OrderedDict()


def _read_claude_session_metadata(
    path: Path,
    *,
    expected_session_id: str,
    expected_agent_id: str | None = None,
    projects_dir: Path,
) -> dict[str, str] | None:
    '''Read only bounded local identity/title/project metadata for one Claude JSONL file'''
    if path.is_symlink() or not path.is_file():
        return None
    try:
        root = projects_dir.resolve(strict=True)
        resolved = path.resolve(strict=True)
        if not _path_is_within(str(resolved), root):
            return None
        stat = resolved.stat()
    except OSError:
        return None
    cache_key = hashlib.sha256(
        f'{resolved}\0{expected_session_id}\0{expected_agent_id or ""}'.encode('utf-8')
    ).hexdigest()
    cached = _CLAUDE_SESSION_METADATA_CACHE.get(cache_key)
    if cached is not None and cached[:2] == (stat.st_size, stat.st_mtime_ns):
        _CLAUDE_SESSION_METADATA_CACHE.move_to_end(cache_key)
        return dict(cached[2]) if cached[2] is not None else None

    try:
        with resolved.open('rb') as stream:
            head = stream.read(CLAUDE_SESSION_HEADER_BYTES)
            if stat.st_size > CLAUDE_SESSION_HEADER_BYTES:
                tail_offset = max(0, stat.st_size - CLAUDE_SESSION_HEADER_BYTES)
                stream.seek(tail_offset)
                tail = stream.read(CLAUDE_SESSION_HEADER_BYTES)
                tail_lines = tail.splitlines()
                if tail_offset and tail_lines:
                    tail_lines = tail_lines[1:]
            else:
                tail_lines = []
    except OSError:
        return None

    session_found = False
    agent_found = expected_agent_id is None
    cwd = ''
    ai_title = ''
    custom_title = ''
    seen_lines: set[bytes] = set()
    for line in head.splitlines() + tail_lines:
        if line in seen_lines:
            continue
        seen_lines.add(line)
        try:
            item = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(item, Mapping):
            continue
        item_session_id = item.get('sessionId') or item.get('session_id')
        if isinstance(item_session_id, str):
            if item_session_id.casefold() != expected_session_id.casefold():
                continue
            session_found = True
        item_agent_id = item.get('agentId')
        if expected_agent_id is not None and item_agent_id == expected_agent_id:
            agent_found = True
        if isinstance(item.get('cwd'), str) and item['cwd'] and not cwd:
            cwd = item['cwd']
        if item.get('type') == 'ai-title' and isinstance(item.get('aiTitle'), str):
            ai_title = item['aiTitle']
        elif item.get('type') == 'custom-title' and isinstance(item.get('customTitle'), str):
            custom_title = item['customTitle']

    result = (
        {'cwd': cwd, 'title': _safe_app_text(custom_title or ai_title, 96)}
        if session_found and agent_found
        else None
    )
    _CLAUDE_SESSION_METADATA_CACHE[cache_key] = (stat.st_size, stat.st_mtime_ns, result)
    _CLAUDE_SESSION_METADATA_CACHE.move_to_end(cache_key)
    while len(_CLAUDE_SESSION_METADATA_CACHE) > 512:
        _CLAUDE_SESSION_METADATA_CACHE.popitem(last=False)
    return dict(result) if result is not None else None


def _read_claude_latest_outputs(payload: object) -> dict[str, str]:
    '''Synthetic/legacy fixture helper; runtime reads Claude session files directly'''
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
    - 📌保留标题/项目；state DB 不含权威逐会话状态，因此 status 固定为 unknown
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


def read_claude_local_sessions(
    *,
    observed_at: datetime,
    sequence: int,
    config_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], str]:
    '''只读读取 Claude Code 项目目录中的会话 JSONL 与子 Agent 日志
    - 📌仅扫描配置目录的项目层 JSONL 和已知 session/subagents/agent-*.jsonl 结构
    - 📌文件名、sessionId 与 agentId 必须匹配；不跟随索引 fullPath 或符号链接
    - 🚩本机文件可读不代表 Claude Code 进程在线；在线状态由宿主进程观察器单独提供
    '''
    projects_dir = _claude_projects_directory(config_dir)
    try:
        root = projects_dir.resolve(strict=True)
        if not root.is_dir():
            raise SourceReadError('claude-code', 'projects_directory_unavailable')
        project_dirs = sorted(
            (
                path for path in root.iterdir()
                if path.is_dir() and not path.is_symlink()
            ),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
    except SourceReadError:
        raise
    except OSError as exc:
        raise SourceReadError('claude-code', 'projects_directory_unavailable') from exc

    partial = len(project_dirs) > CLAUDE_PROJECT_LIMIT
    project_dirs = project_dirs[:CLAUDE_PROJECT_LIMIT]
    main_candidates: list[tuple[float, Path, Path, str]] = []
    for project_dir in project_dirs:
        try:
            files = list(project_dir.glob('*.jsonl'))
        except OSError:
            partial = True
            continue
        for path in files:
            if path.is_symlink() or not path.is_file():
                partial = True
                continue
            try:
                session_id = str(UUID(path.stem))
            except ValueError:
                continue
            try:
                resolved = path.resolve(strict=True)
                if resolved.parent != project_dir.resolve(strict=True):
                    partial = True
                    continue
                modified_at = resolved.stat().st_mtime
            except OSError:
                partial = True
                continue
            main_candidates.append((modified_at, project_dir, resolved, session_id))

    main_candidates.sort(key=lambda value: value[0], reverse=True)
    if len(main_candidates) > CLAUDE_SESSION_FILE_LIMIT:
        partial = True
    main_candidates = main_candidates[:CLAUDE_SESSION_FILE_LIMIT]

    records: list[dict[str, Any]] = []
    main_records: dict[str, tuple[dict[str, Any], str, Path]] = {}
    output_candidates: list[tuple[float, dict[str, Any], Path, str, str | None]] = []
    seen_main_ids: set[str] = set()
    for source_order, (modified_at, project_dir, path, session_id) in enumerate(main_candidates):
        if session_id in seen_main_ids:
            partial = True
            continue
        seen_main_ids.add(session_id)
        metadata = _read_claude_session_metadata(
            path,
            expected_session_id=session_id,
            projects_dir=root,
        )
        if metadata is None:
            partial = True
            continue
        project_label = _project_label_from_cwd(metadata.get('cwd'))
        record = _activity_record(
            source_id='claude-code',
            raw_id=session_id,
            parent_raw_id=None,
            status='history_only',
            normalized_status='unknown',
            authority='unknown',
            sequence=sequence * SOURCE_SEQUENCE_STRIDE + source_order,
            observed_at=observed_at,
            provider_id='claude-code-local-files',
            source_instance_id='claude-code-local-files',
            provenance='approved-log',
        )
        display_suffix = record['session_id'][-6:]
        record['display_name'] = _safe_app_text(metadata.get('title'), 96) or (
            f'Claude Code · {project_label} · {display_suffix}'
            if project_label
            else f'Claude Code 会话 · {display_suffix}'
        )
        record['project_label'] = project_label
        record['source_status'] = 'history_record'
        record['last_output_kind'] = 'unavailable'
        records.append(record)
        main_records[session_id] = (record, project_label, project_dir)
        output_candidates.append((modified_at, record, path, session_id, None))

    child_candidates: list[tuple[float, str, str, Path, str]] = []
    for parent_id, (_, _, project_dir) in main_records.items():
        subagents_dir = project_dir / parent_id / 'subagents'
        if not subagents_dir.exists():
            continue
        if subagents_dir.is_symlink() or not subagents_dir.is_dir():
            partial = True
            continue
        try:
            paths = list(subagents_dir.glob('agent-*.jsonl'))
        except OSError:
            partial = True
            continue
        for path in paths:
            if path.is_symlink() or not path.is_file():
                partial = True
                continue
            agent_id = path.stem.removeprefix('agent-')
            if not agent_id or len(agent_id) > 128 or '/' in agent_id or '\\' in agent_id:
                partial = True
                continue
            try:
                resolved = path.resolve(strict=True)
                if resolved.parent != subagents_dir.resolve(strict=True):
                    partial = True
                    continue
                modified_at = resolved.stat().st_mtime
            except OSError:
                partial = True
                continue
            child_candidates.append((modified_at, parent_id, agent_id, resolved, project_dir))

    child_candidates.sort(key=lambda value: value[0], reverse=True)
    remaining = max(0, MAX_ACTIVITIES - len(records))
    if len(child_candidates) > remaining:
        partial = True
    for modified_at, parent_id, agent_id, path, project_dir in child_candidates[:remaining]:
        metadata = _read_claude_session_metadata(
            path,
            expected_session_id=parent_id,
            expected_agent_id=agent_id,
            projects_dir=root,
        )
        if metadata is None:
            partial = True
            continue
        project_label = (
            _project_label_from_cwd(metadata.get('cwd'))
            or main_records[parent_id][1]
        )
        raw_id = f'{parent_id}/subagent/{agent_id}'
        record = _activity_record(
            source_id='claude-code',
            raw_id=raw_id,
            parent_raw_id=parent_id,
            status='history_record',
            normalized_status='unknown',
            authority='unknown',
            sequence=sequence * SOURCE_SEQUENCE_STRIDE + len(records),
            observed_at=observed_at,
            provider_id='claude-code-local-files',
            source_instance_id='claude-code-local-files',
            provenance='approved-log',
        )
        record['display_name'] = (
            f"Claude Code 子 Agent · {project_label} · {record['session_id'][-6:]}"
            if project_label
            else f"Claude Code 子 Agent · {record['session_id'][-6:]}"
        )
        record['project_label'] = project_label
        record['last_output_kind'] = 'unavailable'
        records.append(record)
        output_candidates.append((modified_at, record, path, parent_id, agent_id))

    output_candidates.sort(key=lambda value: value[0], reverse=True)
    for _, record, path, session_id, agent_id in output_candidates[:CLAUDE_OUTPUT_READ_LIMIT]:
        record['summary'] = _read_claude_last_agent_output(
            session_id,
            projects_dir=root,
            session_path=path,
            expected_agent_id=agent_id,
        )
        if record['summary']:
            record['last_output_kind'] = 'agent_message'
    return records, 'partial' if partial else 'local_state'


def _bound_combined_source_records(
    records_by_source: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, list[dict[str, Any]]], set[str]]:
    '''按全局上限公平保留最近叶会话，并保留其父会话记录
    - 🎯多个独立来源合并后不得突破 activity 协议的总量上限
    - 📌按来源轮转选择；来源顺序按 source_sequence，较小者较新
    - 📌被保留的子 Agent 总是连同完整父链进入快照
    - 🤖容量不足时标记被裁剪来源为 partial，不宣称列表完整
    '''
    total_count = sum(len(records) for records in records_by_source.values())
    if total_count <= MAX_ACTIVITIES:
        return records_by_source, set()

    records_by_identity: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    record_source: dict[tuple[str, str, str, str], str] = {}
    for source_id, records in records_by_source.items():
        for record in records:
            identity = identity_key(record)
            if identity in records_by_identity:
                raise ValueError('duplicate activity identity in combined source snapshot')
            sequence = record.get('source_sequence')
            if not isinstance(sequence, int) or isinstance(sequence, bool):
                raise ValueError('activity source_sequence must be an integer')
            records_by_identity[identity] = record
            record_source[identity] = source_id

    parents: dict[
        tuple[str, str, str, str], tuple[str, str, str, str] | None
    ] = {}
    children: dict[
        tuple[str, str, str, str], set[tuple[str, str, str, str]]
    ] = {identity: set() for identity in records_by_identity}
    for identity, record in records_by_identity.items():
        parent_session_id = record.get('parent_session_id')
        if parent_session_id is None:
            parents[identity] = None
            continue
        if not isinstance(parent_session_id, str) or not parent_session_id:
            raise ValueError('activity parent_session_id must be a non-empty string or null')
        parent = (*identity[:3], parent_session_id)
        if parent not in records_by_identity:
            raise ValueError('activity parent must be present in the combined source snapshot')
        if record_source[parent] != record_source[identity]:
            raise ValueError('activity parent and child must belong to the same source')
        parents[identity] = parent
        children[parent].add(identity)

    for identity in parents:
        visited: set[tuple[str, str, str, str]] = set()
        current: tuple[str, str, str, str] | None = identity
        while current is not None:
            if current in visited:
                raise ValueError('activity parent hierarchy contains a cycle')
            visited.add(current)
            current = parents[current]

    candidates_by_source: dict[str, list[tuple[int, tuple[str, str, str, str]]]] = {}
    for source_id, records in records_by_source.items():
        candidates = [
            (record['source_sequence'], identity_key(record))
            for record in records
            if not children[identity_key(record)]
        ]
        candidates.sort()
        candidates_by_source[source_id] = candidates

    selected: set[tuple[str, str, str, str]] = set()
    selected_count_by_source = {source_id: 0 for source_id in candidates_by_source}
    positions = {source_id: 0 for source_id in candidates_by_source}
    source_order = [
        source_id
        for source_id, records in records_by_source.items()
        if records
    ]
    base_quota, remaining_quota = divmod(MAX_ACTIVITIES, len(source_order))
    quotas = {
        source_id: base_quota + (index < remaining_quota)
        for index, source_id in enumerate(source_order)
    }
    while len(selected) < MAX_ACTIVITIES:
        progressed = False
        for source_id in source_order:
            if len(selected) >= MAX_ACTIVITIES:
                break
            candidates = candidates_by_source[source_id]
            index = positions[source_id]
            if index >= len(candidates) or selected_count_by_source[source_id] >= quotas[source_id]:
                continue
            _, candidate = candidates[index]

            parent_chain: list[tuple[str, str, str, str]] = []
            current = candidate
            while current not in selected:
                parent_chain.append(current)
                parent = parents[current]
                if parent is None:
                    break
                current = parent
            if (
                selected_count_by_source[source_id] + len(parent_chain) > quotas[source_id]
                or len(selected) + len(parent_chain) > MAX_ACTIVITIES
            ):
                continue
            selected.update(parent_chain)
            selected_count_by_source[source_id] += len(parent_chain)
            positions[source_id] = index + 1
            progressed = True
        if not progressed:
            eligible_sources = [
                source_id
                for source_id in source_order
                if positions[source_id] < len(candidates_by_source[source_id])
                and quotas[source_id] < MAX_ACTIVITIES
            ]
            if not eligible_sources:
                break
            for source_id in eligible_sources:
                quotas[source_id] += 1

    bounded_records = {
        source_id: [
            record for record in records
            if identity_key(record) in selected
        ]
        for source_id, records in records_by_source.items()
    }
    truncated_sources = {
        source_id
        for source_id, records in records_by_source.items()
        if len(bounded_records[source_id]) < len(records)
    }
    return bounded_records, truncated_sources


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


def load_live_snapshot(
    previous: LiveSnapshot | None = None,
    *,
    sequence: int = 0,
    now: datetime | None = None,
    enabled_sources: tuple[str, ...] | None = None,
) -> LiveSnapshot:
    '''读取显式选择的本机来源；Codex App 与 Claude Code 只读本机文件并单独观察进程
    - 📌进程在线状态与磁盘数据可读性、来源读取年龄分开投影
    - 📌进程离线不删除可读历史；本机文件不含权威逐会话状态时保持 unknown
    - 📌单源失败只令该来源数据过期，不把兄弟来源标陈旧
    - 🤖未选择的来源不读取或复用旧记录，UI以not_requested明确呈现
    '''
    observed_at = now or datetime.now(timezone.utc)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError('now must include a timezone')
    observed_at = observed_at.astimezone(timezone.utc)
    selected_sources = normalize_live_source_selection(enabled_sources)
    selected_source_ids = set(selected_sources)
    all_sources = tuple(LIVE_SOURCE_LABELS)
    process_states = (
        _local_process_states()
        if selected_source_ids.intersection({'codex-app', 'claude-code'})
        else {}
    )
    readers = {
        'codex': read_codex_threads,
        'claude-code': read_claude_local_sessions,
    }
    previous_records = previous.records_by_source if previous is not None else {}
    source_observed_at = (
        {
            source_id: observed
            for source_id, observed in previous.source_observed_at.items()
            if source_id in selected_source_ids
        }
        if previous is not None
        else {}
    )
    records_by_source: dict[str, list[dict[str, Any]]] = {
        source_id: [] for source_id in all_sources
    }
    health: dict[str, str] = {
        source_id: 'not_requested' for source_id in all_sources
    }
    data_health: dict[str, str] = {
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
            if previous is not None:
                previous_local_records = _codex_app_local_records(
                    previous_records.get('codex-app', [])
                )
                if previous_local_records:
                    local_app_records = _stale_records(previous_local_records)
                if previous_local_records or source_observed_at.get('codex-app') is not None:
                    local_app_health = 'disconnected'
        records_by_source['codex-app'] = local_app_records
        health['codex-app'] = _process_health(process_states.get('codex-app'))
        data_health['codex-app'] = local_app_health
        if local_app_health in {'local_state', 'partial'}:
            source_observed_at['codex-app'] = observed_at
    for source_id, reader in readers.items():
        if source_id not in selected_source_ids:
            continue
        try:
            records, source_data_health = reader(observed_at=observed_at, sequence=sequence)
        except SourceReadError:
            previous_source_records = previous_records.get(source_id, [])
            records_by_source[source_id] = _stale_records(previous_source_records)
            if source_id == 'claude-code':
                health[source_id] = _process_health(process_states.get(source_id))
                data_health[source_id] = (
                    'disconnected'
                    if previous_source_records or source_id in source_observed_at
                    else 'unavailable'
                )
            else:
                health[source_id] = 'disconnected'
                data_health[source_id] = (
                    'disconnected'
                    if previous_source_records or source_id in source_observed_at
                    else 'unavailable'
                )
        else:
            records_by_source[source_id] = records
            if source_id == 'claude-code':
                health[source_id] = _process_health(process_states.get(source_id))
                data_health[source_id] = source_data_health
            else:
                health[source_id] = source_data_health
                data_health[source_id] = 'not_applicable'
            if source_data_health in {'online', 'partial', 'local_state'}:
                source_observed_at[source_id] = observed_at

    records_by_source, truncated_sources = _bound_combined_source_records(records_by_source)
    for source_id in truncated_sources:
        if source_id in {'codex-app', 'claude-code'}:
            if data_health[source_id] in {'local_state', 'partial'}:
                data_health[source_id] = 'partial'
        elif health[source_id] in {'online', 'partial'}:
            health[source_id] = 'partial'

    records = [record for source_records in records_by_source.values() for record in source_records]
    projection = aggregate_activities(records, now=observed_at)
    projection['source_health'] = health
    projection['source_data_health'] = data_health
    projection['source_labels'] = LIVE_SOURCE_LABELS
    mode_parts: list[str] = []
    if 'codex' in selected_source_ids:
        mode_parts.append('Codex CLI 本机状态库只读')
    if 'codex-app' in selected_source_ids:
        app_presence = {
            'online': '进程在线',
            'offline': '进程离线',
            'unknown': '进程状态未知',
        }.get(health['codex-app'], '进程状态未知')
        mode_parts.append(f'Codex App 状态库与 rollout 只读 · {app_presence}')
    else:
        mode_parts.append('Codex App 本轮未查询')
    if 'claude-code' in selected_source_ids:
        claude_presence = {
            'online': '进程在线',
            'offline': '进程离线',
            'unknown': '进程状态未知',
        }.get(health['claude-code'], '进程状态未知')
        mode_parts.append(f'Claude Code 会话索引只读 · {claude_presence}')
    projection['data_mode_label'] = ' · '.join(mode_parts) or '本轮未查询来源'
    projection['codex_app_links_enabled'] = bool(
        'codex-app' in selected_source_ids
        and any(record.get('codex_app_thread_id') for record in records_by_source['codex-app'])
    )
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
