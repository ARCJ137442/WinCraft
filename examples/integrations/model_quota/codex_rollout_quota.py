'''Read Codex quota snapshots from bounded local rollout events.
- 🎯仅解析 token_count 事件中的 rate_limits，不连接 Codex App 或任何网络服务。
- 📌不读取对话正文、命令输出、工具参数、auth.json 或本机 state 数据库。
- 🤖由 Agent 编写，未经人工逐行审阅。
'''
from __future__ import annotations

import heapq
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from codex_quota import codex_not_enabled, normalize_codex_usage


# * === 常量池 === * #

MAX_ROLLOUT_DIRECTORIES: int = 2048
'''📜单次扫描最多遍历的目录数'''

MAX_ROLLOUT_ENTRIES: int = 20_000
'''📜单次目录枚举最多检查的文件与目录项数'''

MAX_ROLLOUT_FILES: int = 256
'''📜最多保留最近修改的 JSONL 候选文件数'''

MAX_ROLLOUT_FILE_TAIL_BYTES: int = 131_072
'''📜每个候选文件最多读取的尾部字节数'''

MAX_ROLLOUT_SCAN_BYTES: int = 16_777_216
'''📜单次扫描最多读取的 JSONL 总字节数'''

MAX_ROLLOUT_LINE_BYTES: int = 131_072
'''📜单条 JSONL 事件最大解析长度'''

MAX_WINDOW_SECONDS: int = 31_536_000
'''📜额度周期最大一年'''

FRESH_FOR_SECONDS: int = 300
'''📜事件五分钟内标为新鲜'''

STALE_FOR_SECONDS: int = 3_600
'''📜事件一小时内仍显示为陈旧快照'''

MAX_FUTURE_SKEW_SECONDS: int = 60
'''📜允许本机时钟最多领先事件时间一分钟'''

MAX_RESET_TIMESTAMP: int = 253_402_300_799
'''📜可表示到 UTC 年 9999 的 Unix 时间戳上限'''


class RolloutQuotaError(RuntimeError):
    '''携带稳定错误码且不包含本机路径或文件内容的读取错误。'''

    def __init__(self, code: str) -> None:
        self.code: str = code
        super().__init__(code)


def __event_timestamp(value: Any) -> datetime | None:
    '''解析带时区的 RFC 3339 事件时间。'''
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def __valid_window(value: Any) -> dict[str, Any] | None:
    '''把 rollout window 投影为 Codex 额度适配器使用的字段。'''
    if not isinstance(value, dict):
        return None
    used_percent = value.get('used_percent')
    window_minutes = value.get('window_minutes')
    resets_at = value.get('resets_at')
    if (
        isinstance(used_percent, bool)
        or not isinstance(used_percent, (int, float))
        or not math.isfinite(used_percent)
        or not 0 <= used_percent <= 100
        or isinstance(window_minutes, bool)
        or not isinstance(window_minutes, int)
        or window_minutes <= 0
        or window_minutes * 60 > MAX_WINDOW_SECONDS
        or isinstance(resets_at, bool)
        or not isinstance(resets_at, int)
        or not 0 < resets_at <= MAX_RESET_TIMESTAMP
    ):
        return None
    return {
        'used_percent': float(used_percent),
        'limit_window_seconds': window_minutes * 60,
        'reset_at': resets_at,
    }


def __quota_event(
    line: bytes,
    now: datetime,
) -> tuple[datetime, int, dict[str, Any]] | None:
    '''只提取 token_count 事件里的额度字段，不把原始行返回给调用方。'''
    if b'"token_count"' not in line:
        return None
    try:
        root = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(root, dict) or root.get('type') != 'event_msg':
        return None
    payload = root.get('payload')
    if not isinstance(payload, dict) or payload.get('type') != 'token_count':
        return None
    timestamp = __event_timestamp(root.get('timestamp'))
    if (
        timestamp is None
        or timestamp > now + timedelta(seconds=MAX_FUTURE_SKEW_SECONDS)
    ):
        return None
    rate_limits = payload.get('rate_limits')
    if not isinstance(rate_limits, dict):
        return None
    primary = __valid_window(rate_limits.get('primary'))
    if primary is None:
        return None
    window_data: dict[str, Any] = {'primary_window': primary}
    secondary = __valid_window(rate_limits.get('secondary'))
    if secondary is not None:
        window_data['secondary_window'] = secondary
    ordinal = root.get('ordinal')
    if (
        isinstance(ordinal, bool)
        or not isinstance(ordinal, int)
        or ordinal < 0
    ):
        ordinal = 0
    return timestamp, ordinal, {'rate_limit': window_data}


def __candidate_rollouts(home: Path) -> list[tuple[int, Path]]:
    '''有界枚举 Codex sessions 与 archived_sessions 下最近修改的 rollout。'''
    newest: list[tuple[int, str, Path]] = []
    entries_seen = 0
    directories_seen = 0
    found_directory = False
    roots: list[Path] = []
    for directory_name in ('sessions', 'archived_sessions'):
        root = home / directory_name
        if not root.is_dir() or root.is_symlink():
            continue
        found_directory = True
        roots.append(root)
    pending = list(roots)
    while (
        pending
        and directories_seen < MAX_ROLLOUT_DIRECTORIES
        and entries_seen < MAX_ROLLOUT_ENTRIES
    ):
        current_path = pending.pop()
        directories_seen += 1
        try:
            entries = os.scandir(current_path)
        except OSError:
            continue
        try:
            with entries:
                for entry in entries:
                    entries_seen += 1
                    if entries_seen > MAX_ROLLOUT_ENTRIES:
                        break
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if (
                                directories_seen + len(pending)
                                < MAX_ROLLOUT_DIRECTORIES
                            ):
                                pending.append(Path(entry.path))
                            continue
                        if (
                            not entry.is_file(follow_symlinks=False)
                            or not entry.name.endswith('.jsonl')
                        ):
                            continue
                        modified_ns = entry.stat(follow_symlinks=False).st_mtime_ns
                    except OSError:
                        continue
                    path = Path(entry.path)
                    item = (modified_ns, str(path), path)
                    if len(newest) < MAX_ROLLOUT_FILES:
                        heapq.heappush(newest, item)
                    elif item > newest[0]:
                        heapq.heapreplace(newest, item)
        except OSError:
            continue
    if not found_directory:
        raise RolloutQuotaError('ROLLOUT_DIRECTORY_MISSING')
    candidates = [(modified_ns, path) for modified_ns, _path_text, path in newest]
    candidates.sort(reverse=True)
    return candidates


def __tail_lines(
    path: Path,
    byte_limit: int,
    now: datetime,
) -> Iterator[tuple[datetime, int, dict[str, Any]]]:
    '''读取单个 rollout 的有界尾部并产出已脱敏额度投影。'''
    try:
        with path.open('rb') as stream:
            stream.seek(0, os.SEEK_END)
            file_size = stream.tell()
            start = max(0, file_size - byte_limit)
            stream.seek(start)
            consumed = 0
            if start:
                while consumed < byte_limit:
                    part = stream.readline(min(MAX_ROLLOUT_LINE_BYTES + 1, byte_limit - consumed))
                    consumed += len(part)
                    if not part or part.endswith(b'\n'):
                        break  # 丢弃从半行开始的截断记录
            remaining = max(0, min(byte_limit - consumed, file_size - stream.tell()))
            discarding_long_line = False
            while remaining > 0:
                line = stream.readline(MAX_ROLLOUT_LINE_BYTES + 1)
                if not line:
                    break
                remaining -= len(line)
                if discarding_long_line:
                    discarding_long_line = not line.endswith(b'\n')
                    continue
                if len(line) > MAX_ROLLOUT_LINE_BYTES:
                    discarding_long_line = not line.endswith(b'\n')
                    continue
                event = __quota_event(line, now)
                if event is not None:
                    yield event
    except OSError:
        return


def read_latest_codex_rollout_quota(
    explicit_home: Path | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    '''从本机 Codex rollout 中读取最新有效 quota 事件。'''
    home = explicit_home.expanduser() if explicit_home is not None else Path(
        os.environ.get('CODEX_HOME', Path.home() / '.codex')
    ).expanduser()
    observed_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    candidates = __candidate_rollouts(home)
    scan_budget = MAX_ROLLOUT_SCAN_BYTES
    latest: tuple[datetime, int, dict[str, Any]] | None = None
    for _modified_ns, path in candidates:
        if scan_budget <= 0:
            break
        limit = min(MAX_ROLLOUT_FILE_TAIL_BYTES, scan_budget)
        try:
            file_size = path.stat().st_size
        except OSError:
            continue
        consumed = min(file_size, limit)
        scan_budget -= consumed
        for event in __tail_lines(path, limit, observed_now):
            if latest is None or event[:2] > latest[:2]:
                latest = event
    if latest is None:
        return None
    timestamp, _ordinal, payload = latest
    projection = normalize_codex_usage(
        payload,
        observed_at=timestamp.isoformat(timespec='seconds').replace('+00:00', 'Z'),
    )
    age_seconds = max(0.0, (observed_now - timestamp).total_seconds())
    if age_seconds <= FRESH_FOR_SECONDS:
        projection['state_label'] = '本机快照'
        projection['freshness_label'] = '新鲜'
        projection['freshness_tone'] = 'success'
    elif age_seconds <= STALE_FOR_SECONDS:
        projection['state_label'] = '本机历史快照'
        projection['state_tone'] = 'warning'
        projection['freshness_label'] = '陈旧'
        projection['freshness_tone'] = 'warning'
    else:
        projection['state_label'] = '本机历史快照'
        projection['state_tone'] = 'muted'
        projection['freshness_label'] = '已过期'
        projection['freshness_tone'] = 'muted'
    projection['observed_at'] = timestamp.isoformat(timespec='seconds').replace('+00:00', 'Z')
    projection['observed_label'] = f"最后事件：{projection['observed_at']}"
    projection['detail'] = '来自本机 token_count quota 事件 · 只读 rollout · 未连接 App 或网络'
    return projection


def __empty_rollout_projection(code: str) -> dict[str, Any]:
    '''返回未知快照状态，不以零值替代缺失。'''
    labels = {
        'ROLLOUT_DIRECTORY_MISSING': '未找到 Codex rollout 目录',
        'NO_QUOTA_EVENT': '尚无 quota 快照',
        'ROLLOUT_READ_FAILED': '本机 quota 快照读取失败',
    }
    return {
        'state_label': labels.get(code, '本机 quota 快照未知'),
        'state_tone': 'muted',
        'freshness_label': '未知',
        'freshness_tone': 'muted',
        'observed_at': None,
        'observed_label': '尚无成功读取时间',
        'detail': '本机 rollout 未提供可验证的 quota 事件；额度保留为未知。',
        'windows': [],
    }


def refresh_codex_rollout_source(
    *,
    enabled: bool,
    explicit_home: Path | None,
    previous: Any,
    now: datetime | None = None,
) -> dict[str, Any]:
    '''读取本机 quota 快照，并在短暂读取失败时保留已标陈旧的 last-good。'''
    if not enabled:
        return codex_not_enabled()
    try:
        projection = read_latest_codex_rollout_quota(explicit_home, now=now)
    except RolloutQuotaError as error:
        projection = None
        code = error.code
    else:
        code = 'NO_QUOTA_EVENT'
    if projection is not None:
        return projection
    if isinstance(previous, dict) and previous.get('windows'):
        stale = dict(previous)
        stale['state_label'] = '保留上次快照'
        stale['state_tone'] = 'warning'
        stale['freshness_label'] = '读取失败'
        stale['freshness_tone'] = 'warning'
        stale['detail'] = '本轮未取得更新的 quota 事件；仍显示已标记时间的上次本机快照。'
        return stale
    return __empty_rollout_projection(code)
