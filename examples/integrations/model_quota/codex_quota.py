"""Opt-in Codex account adapter using credentials from the local Codex home.

The upstream ChatGPT usage route is not a documented public API. This adapter
therefore stays opt-in, uses one fixed HTTPS GET, and treats schema changes as
unknown/error rather than inferring quota from local session history.
"""
from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CODEX_USAGE_ENDPOINT = "https://chatgpt.com/backend-api/wham/usage"
MAX_AUTH_BYTES = 1_048_576
MAX_RESPONSE_BYTES = 262_144
MAX_TOKEN_CHARS = 65_536
MAX_ACCOUNT_ID_CHARS = 256
SECONDS_PER_DAY = 86_400
SECONDS_PER_HOUR = 3_600
SECONDS_PER_MINUTE = 60
WEEK_WINDOW_SECONDS = 7 * SECONDS_PER_DAY
MAX_WINDOW_SECONDS = 31_536_000
REQUEST_TIMEOUT_SECONDS = 6

ERROR_LABELS = {
    "AUTH_FILE_UNAVAILABLE": "本机 Codex 登录文件不可读",
    "AUTH_FILE_INVALID": "本机 Codex 登录文件无效",
    "AUTH_FIELDS_MISSING": "本机 Codex 登录字段缺失",
    "AUTH_REJECTED": "Codex 登录凭据已失效",
    "ACCOUNT_CHANGED": "读取期间检测到账号切换，旧读数已清除",
    "REQUEST_TIMEOUT": "Codex 额度读取超时",
    "NETWORK_ERROR": "Codex 额度接口暂不可达",
    "REDIRECT_BLOCKED": "Codex 额度接口重定向已拒绝",
    "UPSTREAM_REJECTED": "Codex 额度接口拒绝请求",
    "RESPONSE_TOO_LARGE": "Codex 额度响应超过大小限制",
    "INVALID_JSON": "Codex 额度响应不是有效 JSON",
    "INVALID_RESPONSE": "Codex 额度响应格式无效",
    "PRIMARY_WINDOW_MISSING": "Codex 响应没有主额度窗口",
    "PRIMARY_WINDOW_INVALID": "Codex 主额度窗口字段无效",
}

_ACCOUNT_BOUNDARY_ERRORS = {
    "AUTH_FILE_UNAVAILABLE",
    "AUTH_FILE_INVALID",
    "AUTH_FIELDS_MISSING",
    "ACCOUNT_CHANGED",
}


class CodexQuotaError(RuntimeError):
    """A stable, sanitized error category; never retains upstream text."""

    def __init__(self, code: str) -> None:
        self.code = code if code in ERROR_LABELS else "NETWORK_ERROR"
        super().__init__(self.code)


@dataclass(frozen=True)
class _AuthCredentials:
    access_token: str = field(repr=False)
    account_id: str = field(repr=False)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Do not forward an account bearer token to a redirected host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def codex_home(explicit_home: Path | None = None) -> Path:
    """Resolve only the standard Codex home or an explicitly supplied home."""
    if explicit_home is not None:
        return explicit_home.expanduser()
    configured_home = os.environ.get("CODEX_HOME")
    return Path(configured_home).expanduser() if configured_home else Path.home() / ".codex"


def _load_auth_credentials(auth_file: Path) -> _AuthCredentials:
    try:
        if auth_file.is_symlink():
            raise CodexQuotaError("AUTH_FILE_INVALID")
        if auth_file.stat().st_size > MAX_AUTH_BYTES:
            raise CodexQuotaError("AUTH_FILE_INVALID")
        encoded = auth_file.read_bytes()
    except CodexQuotaError:
        raise
    except OSError:
        raise CodexQuotaError("AUTH_FILE_UNAVAILABLE") from None
    if len(encoded) > MAX_AUTH_BYTES:
        raise CodexQuotaError("AUTH_FILE_INVALID")
    try:
        payload = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CodexQuotaError("AUTH_FILE_INVALID") from None
    tokens = payload.get("tokens") if isinstance(payload, Mapping) else None
    if not isinstance(tokens, Mapping):
        raise CodexQuotaError("AUTH_FIELDS_MISSING")
    access_token = tokens.get("access_token")
    account_id = tokens.get("account_id")
    if (
        not isinstance(access_token, str)
        or not access_token
        or len(access_token) > MAX_TOKEN_CHARS
        or any(character.isspace() or not character.isprintable() for character in access_token)
        or not isinstance(account_id, str)
        or not account_id
        or len(account_id) > MAX_ACCOUNT_ID_CHARS
        or any(character.isspace() or not character.isprintable() for character in account_id)
    ):
        raise CodexQuotaError("AUTH_FIELDS_MISSING")
    # Deliberately ignore id_token, refresh_token and all other auth fields.
    return _AuthCredentials(access_token=access_token, account_id=account_id)


def _assert_auth_account_unchanged(auth_file: Path, expected_account_id: str) -> None:
    current = _load_auth_credentials(auth_file)
    if current.account_id != expected_account_id:
        raise CodexQuotaError("ACCOUNT_CHANGED")


def _valid_number(value: Any, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, int):
        if not minimum <= value <= maximum:
            return None
        return float(value)
    if not math.isfinite(value) or not minimum <= value <= maximum:
        return None
    return float(value)


def _valid_integer(value: Any, minimum: int, maximum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        return None
    return value


def _window_label(window_id: str, duration_seconds: int) -> str:
    if duration_seconds % SECONDS_PER_DAY == 0:
        duration = f"{duration_seconds // SECONDS_PER_DAY} 天"
    elif duration_seconds % SECONDS_PER_HOUR == 0:
        duration = f"{duration_seconds // SECONDS_PER_HOUR} 小时"
    elif duration_seconds % SECONDS_PER_MINUTE == 0:
        duration = f"{duration_seconds // SECONDS_PER_MINUTE} 分钟"
    else:
        duration = f"{duration_seconds} 秒"
    if window_id == "secondary" and duration_seconds == WEEK_WINDOW_SECONDS:
        kind = "周周期"
    elif window_id == "primary":
        kind = "主窗口"
    else:
        kind = "额外窗口"
    return f"{duration} · {kind}"


def _window_projection(window_id: str, raw: Any, *, required: bool) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        if required:
            raise CodexQuotaError("PRIMARY_WINDOW_MISSING")
        return None
    used_percent = _valid_number(raw.get("used_percent"), 0.0, 100.0)
    duration_seconds = _valid_integer(raw.get("limit_window_seconds"), 1, MAX_WINDOW_SECONDS)
    reset_epoch = _valid_integer(raw.get("reset_at"), 1, 4_102_444_800)
    if used_percent is None or duration_seconds is None or reset_epoch is None:
        if required:
            raise CodexQuotaError("PRIMARY_WINDOW_INVALID")
        return None
    try:
        resets_at = datetime.fromtimestamp(reset_epoch, timezone.utc).isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        if required:
            raise CodexQuotaError("PRIMARY_WINDOW_INVALID") from None
        return None
    remaining_percent = 100.0 - used_percent
    return {
        "id": window_id,
        "label": _window_label(window_id, duration_seconds),
        "used_percent": used_percent,
        "remaining_percent": remaining_percent,
        "value": remaining_percent,
        "maximum": 100,
        "window_seconds": duration_seconds,
        "resets_at": resets_at,
        "detail": f"剩余 {remaining_percent:g}% · 重置 {resets_at}",
    }


def normalize_codex_usage(payload: Any, *, observed_at: str, demo: bool = False) -> dict[str, Any]:
    """Project only bounded quota windows; never include account or credential data."""
    rate_limit = payload.get("rate_limit") if isinstance(payload, Mapping) else None
    if not isinstance(rate_limit, Mapping):
        raise CodexQuotaError("PRIMARY_WINDOW_MISSING")
    primary = _window_projection("primary", rate_limit.get("primary_window"), required=True)
    assert primary is not None
    windows = [primary]
    secondary = _window_projection("secondary", rate_limit.get("secondary_window"), required=False)
    if secondary is not None:
        windows.append(secondary)
    observed = observed_at.replace("+00:00", "Z")
    return {
        "state_label": "合成读数" if demo else "额度已读取",
        "state_tone": "accent" if demo else "success",
        "freshness_label": "合成数据" if demo else "刚刚读取",
        "freshness_tone": "accent" if demo else "success",
        "observed_at": observed,
        "observed_label": f"最近读取：{observed}",
        "detail": "合成数据 · 无网络请求" if demo else "本机授权的实验性来源 · 额度来自固定远端 GET",
        "windows": windows,
    }


def codex_not_enabled() -> dict[str, Any]:
    return {
        "state_label": "未启用",
        "state_tone": "muted",
        "freshness_label": "尚未读取",
        "freshness_tone": "muted",
        "observed_at": None,
        "observed_label": "尚无成功读取时间",
        "detail": "Codex 本机配额来源未启用；不会从会话历史推算。",
        "windows": [],
    }


def with_codex_read_error(previous: Any, code: str) -> dict[str, Any]:
    """Keep last-good windows only when the same local account can still be proven."""
    safe_previous = previous if isinstance(previous, Mapping) else codex_not_enabled()
    clear_previous = code in _ACCOUNT_BOUNDARY_ERRORS
    windows = [] if clear_previous else safe_previous.get("windows", [])
    if not isinstance(windows, list):
        windows = []
    observed_at = None if clear_previous else safe_previous.get("observed_at")
    observed_label = (
        "账号状态不明确，已清除旧读数"
        if clear_previous
        else safe_previous.get("observed_label", "尚无成功读取时间")
    )
    return {
        "state_label": "读取失败",
        "state_tone": "danger",
        "freshness_label": "没有新读数",
        "freshness_tone": "danger",
        "observed_at": observed_at,
        "observed_label": observed_label,
        "detail": ERROR_LABELS.get(code, ERROR_LABELS["NETWORK_ERROR"]),
        "windows": windows,
    }


def fetch_codex_quota(explicit_home: Path | None = None) -> dict[str, Any]:
    """Read the opt-in Codex auth file and perform only the fixed HTTPS GET."""
    auth_file = codex_home(explicit_home) / "auth.json"
    credentials = _load_auth_credentials(auth_file)
    request = urllib.request.Request(
        CODEX_USAGE_ENDPOINT,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {credentials.access_token}",
            "ChatGPT-Account-Id": credentials.account_id,
            "User-Agent": "codex-cli",
            "OpenAI-Beta": "codex-1",
            "originator": "codex_cli_rs",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        response = opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS)
    except urllib.error.HTTPError as error:
        _assert_auth_account_unchanged(auth_file, credentials.account_id)
        if error.code in {401, 403}:
            raise CodexQuotaError("AUTH_REJECTED") from None
        if 300 <= error.code < 400:
            raise CodexQuotaError("REDIRECT_BLOCKED") from None
        raise CodexQuotaError("UPSTREAM_REJECTED") from None
    except TimeoutError:
        _assert_auth_account_unchanged(auth_file, credentials.account_id)
        raise CodexQuotaError("REQUEST_TIMEOUT") from None
    except (urllib.error.URLError, OSError):
        _assert_auth_account_unchanged(auth_file, credentials.account_id)
        raise CodexQuotaError("NETWORK_ERROR") from None

    try:
        with response:
            status = getattr(response, "status", 200)
            if status in {401, 403}:
                _assert_auth_account_unchanged(auth_file, credentials.account_id)
                raise CodexQuotaError("AUTH_REJECTED")
            if 300 <= status < 400:
                _assert_auth_account_unchanged(auth_file, credentials.account_id)
                raise CodexQuotaError("REDIRECT_BLOCKED")
            if status != 200:
                _assert_auth_account_unchanged(auth_file, credentials.account_id)
                raise CodexQuotaError("UPSTREAM_REJECTED")
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    if int(content_length) > MAX_RESPONSE_BYTES:
                        _assert_auth_account_unchanged(auth_file, credentials.account_id)
                        raise CodexQuotaError("RESPONSE_TOO_LARGE")
                except ValueError:
                    _assert_auth_account_unchanged(auth_file, credentials.account_id)
                    raise CodexQuotaError("INVALID_RESPONSE") from None
            encoded = response.read(MAX_RESPONSE_BYTES + 1)
    except CodexQuotaError:
        raise
    except (TimeoutError, urllib.error.URLError, OSError):
        _assert_auth_account_unchanged(auth_file, credentials.account_id)
        raise CodexQuotaError("NETWORK_ERROR") from None

    _assert_auth_account_unchanged(auth_file, credentials.account_id)
    if len(encoded) > MAX_RESPONSE_BYTES:
        raise CodexQuotaError("RESPONSE_TOO_LARGE")
    try:
        payload = json.loads(encoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CodexQuotaError("INVALID_JSON") from None
    observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return normalize_codex_usage(payload, observed_at=observed_at)


def refresh_codex_source(
    *,
    enabled: bool,
    explicit_home: Path | None,
    previous: Any,
) -> dict[str, Any]:
    """Keep the default source disabled and sanitize any opt-in read failure."""
    if not enabled:
        return codex_not_enabled()
    try:
        return fetch_codex_quota(explicit_home)
    except CodexQuotaError as error:
        return with_codex_read_error(previous, error.code)


def synthetic_codex_quota(*, observed_at: str) -> dict[str, Any]:
    """Produce clearly synthetic windows without reading credentials or networking."""
    now = datetime.now(timezone.utc)
    payload = {
        "rate_limit": {
            "primary_window": {
                "used_percent": 34,
                "limit_window_seconds": 18_000,
                "reset_at": int(now.timestamp()) + 2 * 60 * 60,
            },
            "secondary_window": {
                "used_percent": 61,
                "limit_window_seconds": WEEK_WINDOW_SECONDS,
                "reset_at": int(now.timestamp()) + 2 * 24 * 60 * 60,
            },
        },
    }
    return normalize_codex_usage(payload, observed_at=observed_at, demo=True)
