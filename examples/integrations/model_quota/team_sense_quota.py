"""Read-only TeamSense model-quota projection and WinCraft scene builder.

Only the documented data:read endpoint is consumed. No provider credentials,
business identifiers, or raw response bodies are written to disk or logs.
"""
from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

MAX_RESPONSE_BYTES = 1_048_576
MAX_MODELS = 8
MAX_BALANCES = 4
MAX_SAFE_INTEGER = 9_007_199_254_740_991
REQUEST_TIMEOUT_SECONDS = 6

FRESHNESS_LABELS = {
    "fresh": ("新鲜", "success"),
    "stale": ("陈旧", "warning"),
    "expired": ("已过期", "danger"),
    "empty": ("无缓存", "muted"),
}
UPSTREAM_LABELS = {
    "healthy": ("来源可用", "success"),
    "degraded": ("来源降级", "warning"),
    "offline": ("来源离线", "danger"),
    "unknown": ("来源状态未知", "muted"),
}
WINDOW_STATE_LABELS = {
    "metered": "按量",
    "exhausted": "已耗尽",
    "unlimited": "不限量",
    "not_in_plan": "不在方案内",
    "unknown": "额度未知",
}


class TeamSenseApiError(RuntimeError):
    """A bounded error category that never includes request headers or response text."""

    def __init__(self, code: str) -> None:
        self.code = code if code in {
            "HTTP_401", "HTTP_403", "HTTP_404", "HTTP_429", "HTTP_ERROR",
            "NETWORK_ERROR", "RESPONSE_TOO_LARGE", "INVALID_JSON", "INVALID_RESPONSE",
        } else "NETWORK_ERROR"
        super().__init__(self.code)


API_ERROR_LABELS = {
    "NOT_CONFIGURED": "未配置 TeamSense 连接",
    "HTTP_401": "凭据未被接受",
    "HTTP_403": "token 缺少 data:read 权限",
    "HTTP_404": "只读接口路径不存在",
    "HTTP_429": "读取频率受限",
    "HTTP_ERROR": "TeamSense 返回 HTTP 错误",
    "NETWORK_ERROR": "网络或 TLS 连接失败",
    "RESPONSE_TOO_LARGE": "接口响应超过本机上限",
    "INVALID_JSON": "接口响应不是有效 JSON",
    "INVALID_RESPONSE": "接口响应结构无效",
}


def validate_base_url(value: str) -> str:
    """Require TLS remotely; permit cleartext only for an explicit loopback address."""
    parsed = urllib.parse.urlsplit(value.strip())
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("base URL must be an origin without credentials, path, query, or fragment")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("base URL port is invalid") from exc
    if parsed.scheme == "http":
        try:
            loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise ValueError("cleartext HTTP is allowed only for a loopback IP")
    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    authority = f"{host}:{port}" if port is not None else host
    return f"{parsed.scheme}://{authority}"


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Do not forward a bearer token through an HTTP redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def fetch_team_sense_models(base_url: str, token: str) -> dict[str, Any]:
    """Fetch the cache-backed GET endpoint; never trigger a refresh/write route."""
    origin = validate_base_url(base_url)
    if not token or len(token) > 4096 or any(character.isspace() for character in token):
        raise TeamSenseApiError("INVALID_RESPONSE")
    request = urllib.request.Request(
        f"{origin}/v1/integrations/models",
        headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
        method="GET",
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", 200)
            if status != 200:
                raise TeamSenseApiError(_http_error_code(status))
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > MAX_RESPONSE_BYTES:
                raise TeamSenseApiError("RESPONSE_TOO_LARGE")
            encoded = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise TeamSenseApiError(_http_error_code(exc.code)) from None
    except ValueError:
        raise TeamSenseApiError("INVALID_RESPONSE") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise TeamSenseApiError("NETWORK_ERROR") from None
    if len(encoded) > MAX_RESPONSE_BYTES:
        raise TeamSenseApiError("RESPONSE_TOO_LARGE")
    try:
        payload = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TeamSenseApiError("INVALID_JSON") from None
    if not isinstance(payload, dict):
        raise TeamSenseApiError("INVALID_RESPONSE")
    return payload


def _http_error_code(status: int) -> str:
    return f"HTTP_{status}" if status in {401, 403, 404, 429} else "HTTP_ERROR"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_text(value: Any, fallback: str = "") -> str:
    if not isinstance(value, str):
        return fallback
    normalized = " ".join("".join(char for char in value if char.isprintable()).split())
    return normalized[:80] or fallback


def _safe_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value


def _source_meta(raw: Any) -> dict[str, str]:
    meta = _mapping(raw)
    freshness = meta.get("freshness")
    upstream = meta.get("upstreamState")
    if not isinstance(freshness, str):
        freshness = None
    if not isinstance(upstream, str):
        upstream = None
    freshness_label, freshness_tone = FRESHNESS_LABELS.get(
        freshness, ("新鲜度未知", "muted")
    )
    upstream_label, upstream_tone = UPSTREAM_LABELS.get(
        upstream, ("来源状态未知", "muted")
    )
    fetched_at = _safe_timestamp(meta.get("fetchedAt"))
    return {
        "freshness_label": freshness_label,
        "freshness_tone": freshness_tone,
        "upstream_label": upstream_label,
        "upstream_tone": upstream_tone,
        "updated_at": f"缓存更新时间：{fetched_at}" if fetched_at else "缓存更新时间未知",
    }


def _valid_non_negative_integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or value > MAX_SAFE_INTEGER:
        return None
    return value


def _currency_display(currency: str, micros: int) -> str:
    amount = (Decimal(micros) / Decimal(1_000_000)).quantize(Decimal("0.01"))
    symbol = "¥" if currency == "CNY" else "$"
    return f"{symbol}{amount:,.2f}"


def _deepseek_balances(raw_balance: Any) -> tuple[str, list[dict[str, str]]]:
    balance = _mapping(raw_balance)
    available = balance.get("isAvailable")
    if raw_balance is None:
        return "无余额快照", []
    if available is not True:
        return ("余额来源不可用" if available is False else "余额状态未知"), []
    raw_items = balance.get("balances")
    if not isinstance(raw_items, list):
        return "余额数据未知", []
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_items:
        record = _mapping(item)
        currency = record.get("currency")
        amount = _valid_non_negative_integer(record.get("totalMicros"))
        if not isinstance(currency, str) or currency not in {"CNY", "USD"} or amount is None or currency in seen:
            continue
        seen.add(currency)
        items.append({"currency": currency, "display": _currency_display(currency, amount)})
        if len(items) >= MAX_BALANCES:
            break
    return ("余额快照" if items else "余额字段缺失或无效"), items


def _quota_window(model_name: str, window: str, raw: Any) -> dict[str, Any]:
    record = _mapping(raw)
    state = record.get("state")
    if not isinstance(state, str):
        state = None
    status_label = WINDOW_STATE_LABELS.get(state, "额度未知")
    remaining_percent = record.get("remainingPercent")
    remaining_count = _valid_non_negative_integer(record.get("remainingCount"))
    total_count = _valid_non_negative_integer(record.get("totalCount"))
    value: int | float | None = None
    maximum: int | float | None = None
    detail = status_label
    if state in {"exhausted", "unlimited", "not_in_plan"}:
        # Prefer the provider's categorical state; do not contradict it with a stale meter.
        pass
    elif (
        isinstance(remaining_percent, (int, float))
        and not isinstance(remaining_percent, bool)
        and 0 <= remaining_percent <= 100
    ):
        value = remaining_percent
        maximum = 100
        detail = f"剩余 {remaining_percent:g}%"
    elif remaining_count is not None and total_count is not None and total_count > 0 and remaining_count <= total_count:
        value = remaining_count
        maximum = total_count
        detail = f"剩余 {remaining_count:,} / {total_count:,} 次"
    else:
        status_label = "额度未知"
        detail = status_label
    reset_at = _safe_timestamp(record.get("resetsAt"))
    if reset_at:
        detail = f"{detail} · 重置 {reset_at}"
    elif value is not None:
        detail = f"{detail} · 重置时间未知"
    return {
        "model": model_name,
        "window": window,
        "label": f"{model_name} · {window}",
        "value": value,
        "maximum": maximum,
        "status_label": status_label,
        "detail": detail,
    }


def _minimax_windows(raw_quota: Any) -> tuple[str, list[dict[str, Any]], int]:
    quota = _mapping(raw_quota)
    if raw_quota is None:
        return "无额度快照", [], 0
    available = quota.get("isAvailable")
    if available is not True:
        return ("额度来源不可用" if available is False else "额度状态未知"), [], 0
    models = quota.get("models")
    if not isinstance(models, list):
        return "额度数据未知", [], 0
    windows: list[dict[str, Any]] = []
    omitted_models = max(0, len(models) - MAX_MODELS)
    for model in models[:MAX_MODELS]:
        record = _mapping(model)
        name = _safe_text(record.get("name"), "未命名模型")
        windows.append(_quota_window(name, "当前周期", record.get("interval")))
        windows.append(_quota_window(name, "周周期", record.get("weekly")))
    return ("模型周期额度" if windows else "没有可显示的模型额度"), windows, omitted_models


def _api_read_state(
    *,
    api_connected: bool,
    api_observed_at: str | None,
    api_error_code: str | None,
    demo: bool,
) -> dict[str, str | None]:
    observed_at = _safe_timestamp(api_observed_at)
    if demo:
        api_state_label, api_tone = "合成演示数据", "accent"
        api_detail = "无网络请求 · 合成数据"
    elif api_connected:
        api_state_label, api_tone = "TeamSense API 可读", "success"
        api_detail = "读取成功 · 仅使用缓存 GET"
    elif api_error_code == "NOT_CONFIGURED":
        api_state_label, api_tone = "TeamSense 未配置", "muted"
        api_detail = "本面板可以单独读取已显式启用的本机来源"
    else:
        api_state_label, api_tone = "TeamSense API 不可达", "danger"
        api_detail = API_ERROR_LABELS.get(api_error_code or "NETWORK_ERROR", "TeamSense API 不可达")
    safe_error = api_error_code if isinstance(api_error_code, str) and api_error_code in API_ERROR_LABELS else None
    return {
        "state_label": api_state_label,
        "state_tone": api_tone,
        "observed_at": f"最近读取：{observed_at}" if observed_at else "最近读取时间未知",
        "detail": api_detail,
        "error_code": safe_error,
    }


def with_api_read_state(
    projection: Mapping[str, Any],
    *,
    api_connected: bool,
    api_observed_at: str | None,
    api_error_code: str | None = None,
) -> dict[str, Any]:
    """Update only connection state while retaining a redacted last-good projection."""
    safe_projection = dict(projection)
    safe_projection["api"] = _api_read_state(
        api_connected=api_connected,
        api_observed_at=api_observed_at,
        api_error_code=api_error_code,
        demo=False,
    )
    return safe_projection


def normalize_models_snapshot(
    payload: Any,
    *,
    api_connected: bool,
    api_observed_at: str | None = None,
    api_error_code: str | None = None,
    demo: bool = False,
) -> dict[str, Any]:
    """Project only display-safe, bounded fields; never infer an account or quota."""
    if not isinstance(payload, Mapping):
        payload = {}
    deepseek = _mapping(payload.get("deepseek"))
    minimax = _mapping(payload.get("minimax"))
    sub2api = _mapping(payload.get("sub2api"))
    deepseek_state, balances = _deepseek_balances(deepseek.get("balance"))
    minimax_state, windows, omitted_models = _minimax_windows(minimax.get("quota"))
    deepseek_meta = _source_meta(deepseek.get("meta"))
    minimax_meta = _source_meta(minimax.get("meta"))
    sub2api_meta = _source_meta(sub2api.get("meta"))
    return {
        "api": _api_read_state(
            api_connected=api_connected,
            api_observed_at=api_observed_at,
            api_error_code=api_error_code,
            demo=demo,
        ),
        "identity_scope": "当前 TeamSense 连接；接口未返回账户标识",
        "deepseek": {
            **deepseek_meta,
            "state_label": deepseek_state,
            "balances": balances,
        },
        "minimax": {
            **minimax_meta,
            "state_label": minimax_state,
            "windows": windows,
            "omitted_model_count": omitted_models,
            "omitted_models_label": f"另有 {omitted_models} 个模型未显示" if omitted_models else "",
        },
        "sub2api": {
            **sub2api_meta,
            "state_label": "管理快照不是额度余额",
        },
        "codex": {
            "state_label": "未启用",
            "state_tone": "muted",
            "freshness_label": "尚未读取",
            "freshness_tone": "muted",
            "observed_at": None,
            "observed_label": "尚无成功读取时间",
            "detail": "Codex 本机配额来源未启用；不会从会话历史推算。",
            "windows": [],
        },
        "sources": ["deepseek", "minimax", "sub2api"],
    }


def _node(node_id: str, kind: str, props: dict[str, Any] | None = None,
          children: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"id": node_id, "kind": kind, "props": props or {}, "children": children or []}


def _bound(path: str) -> dict[str, str]:
    return {"$path": path}


def build_quota_scene(projection: Mapping[str, Any]) -> dict[str, Any]:
    """Build a compact dashboard; model and quota-window identity stay visible."""
    data = dict(projection)
    deepseek = _mapping(data.get("deepseek"))
    minimax = _mapping(data.get("minimax"))
    codex = _mapping(data.get("codex"))
    deepseek_balances = deepseek.get("balances") if isinstance(deepseek.get("balances"), list) else []
    deepseek_children = [
        _node(
            f"quota-deepseek-balance-{index}",
            "metric",
            {
                "label": f"DeepSeek · {item['currency']} 余额",
                "value": _bound(f"/deepseek/balances/{index}/display"),
                "caption": "余额，不代表订阅总额度",
            },
        )
        for index, item in enumerate(deepseek_balances)
        if isinstance(item, Mapping)
    ]
    if not deepseek_children:
        deepseek_children.append(
            _node("quota-deepseek-empty", "text", {"text": _bound("/deepseek/state_label"), "size": "small"})
        )

    minimax_windows = minimax.get("windows") if isinstance(minimax.get("windows"), list) else []
    minimax_children: list[dict[str, Any]] = []
    for index, item in enumerate(minimax_windows):
        if not isinstance(item, Mapping):
            continue
        if isinstance(item.get("value"), (int, float)) and isinstance(item.get("maximum"), (int, float)):
            minimax_children.append(
                _node(
                    f"quota-minimax-window-{index}",
                    "progress",
                    {
                        "label": _bound(f"/minimax/windows/{index}/label"),
                        "value": _bound(f"/minimax/windows/{index}/value"),
                        "max": _bound(f"/minimax/windows/{index}/maximum"),
                    },
                )
            )
            minimax_children.append(
                _node(
                    f"quota-minimax-detail-{index}",
                    "text",
                    {"text": _bound(f"/minimax/windows/{index}/detail"), "size": "small"},
                )
            )
        else:
            minimax_children.append(
                _node(
                    f"quota-minimax-window-{index}",
                    "text",
                    {"text": _bound(f"/minimax/windows/{index}/detail"), "size": "small"},
                )
            )
    if not minimax_children:
        minimax_children.append(
            _node("quota-minimax-empty", "text", {"text": _bound("/minimax/state_label"), "size": "small"})
        )
    if minimax.get("omitted_model_count", 0) > 0:
        minimax_children.append(
            _node(
                "quota-minimax-omitted-models",
                "text",
                {"text": _bound("/minimax/omitted_models_label"), "size": "small"},
            )
        )

    codex_windows = codex.get("windows") if isinstance(codex.get("windows"), list) else []
    codex_children: list[dict[str, Any]] = []
    for index, item in enumerate(codex_windows[:2]):
        if not isinstance(item, Mapping):
            continue
        if isinstance(item.get("value"), (int, float)) and isinstance(item.get("maximum"), (int, float)):
            codex_children.append(
                _node(
                    f"quota-codex-window-{index}",
                    "progress",
                    {
                        "label": _bound(f"/codex/windows/{index}/label"),
                        "value": _bound(f"/codex/windows/{index}/value"),
                        "max": _bound(f"/codex/windows/{index}/maximum"),
                    },
                )
            )
            codex_children.append(
                _node(
                    f"quota-codex-detail-{index}",
                    "text",
                    {"text": _bound(f"/codex/windows/{index}/detail"), "size": "small"},
                )
            )
    if not codex_children:
        codex_children.append(
            _node("quota-codex-empty", "text", {"text": _bound("/codex/detail"), "size": "small"})
        )

    root = _node(
        "quota-panel-root",
        "stack",
        {"gap": 10},
        [
            _node(
                "quota-panel-heading",
                "row",
                {"gap": 10},
                [
                    _node("quota-panel-title", "text", {"text": "模型额度", "size": "title"}),
                    _node(
                        "quota-api-state",
                        "badge",
                        {"text": _bound("/api/state_label"), "tone": _bound("/api/state_tone")},
                    ),
                ],
            ),
            _node(
                "quota-api-observed-at",
                "text",
                {"text": _bound("/api/observed_at"), "size": "small"},
            ),
            _node(
                "quota-api-detail",
                "text",
                {"text": _bound("/api/detail"), "size": "small"},
            ),
            _node(
                "quota-identity-scope",
                "text",
                {"text": _bound("/identity_scope"), "size": "small"},
            ),
            _node("quota-divider-primary", "divider"),
            _node(
                "quota-deepseek",
                "stack",
                {"gap": 6},
                [
                    _node(
                        "quota-deepseek-heading",
                        "row",
                        {"gap": 8},
                        [
                            _node("quota-deepseek-title", "text", {"text": "DeepSeek", "size": "heading"}),
                            _node(
                                "quota-deepseek-freshness",
                                "badge",
                                {
                                    "text": _bound("/deepseek/freshness_label"),
                                    "tone": _bound("/deepseek/freshness_tone"),
                                },
                            ),
                        ],
                    ),
                    _node(
                        "quota-deepseek-source-state",
                        "text",
                        {
                            "text": _bound("/deepseek/upstream_label"),
                            "size": "small",
                        },
                    ),
                    _node("quota-deepseek-balances", "row", {"gap": 10}, deepseek_children),
                    _node(
                        "quota-deepseek-updated",
                        "text",
                        {"text": _bound("/deepseek/updated_at"), "size": "small"},
                    ),
                ],
            ),
            _node("quota-divider-secondary", "divider"),
            _node(
                "quota-minimax",
                "stack",
                {"gap": 6},
                [
                    _node(
                        "quota-minimax-heading",
                        "row",
                        {"gap": 8},
                        [
                            _node("quota-minimax-title", "text", {"text": "MiniMax", "size": "heading"}),
                            _node(
                                "quota-minimax-freshness",
                                "badge",
                                {
                                    "text": _bound("/minimax/freshness_label"),
                                    "tone": _bound("/minimax/freshness_tone"),
                                },
                            ),
                        ],
                    ),
                    _node(
                        "quota-minimax-source-state",
                        "text",
                        {"text": _bound("/minimax/upstream_label"), "size": "small"},
                    ),
                    _node("quota-minimax-windows", "stack", {"gap": 5}, minimax_children),
                    _node(
                        "quota-minimax-updated",
                        "text",
                        {"text": _bound("/minimax/updated_at"), "size": "small"},
                    ),
                ],
            ),
            _node("quota-divider-tertiary", "divider"),
            _node(
                "quota-codex",
                "stack",
                {"gap": 5},
                [
                    _node(
                        "quota-codex-heading",
                        "row",
                        {"gap": 8},
                        [
                            _node("quota-codex-title", "text", {"text": "Codex", "size": "heading"}),
                            _node(
                                "quota-codex-state",
                                "badge",
                                {
                                    "text": _bound("/codex/state_label"),
                                    "tone": _bound("/codex/state_tone"),
                                },
                            ),
                        ],
                    ),
                    _node(
                        "quota-codex-freshness",
                        "text",
                        {"text": _bound("/codex/observed_label"), "size": "small"},
                    ),
                    *codex_children,
                    _node(
                        "quota-codex-source-note",
                        "text",
                        {"text": _bound("/codex/detail"), "size": "small"},
                    ),
                ],
            ),
            _node(
                "quota-panel-footer",
                "text",
                {
                    "text": "各来源、币种与额度周期独立显示；Codex 为本机实验性只读源。",
                    "size": "small",
                },
            ),
        ],
    )
    return {
        "root": root,
        "data": data,
        "theme": {
            "background": "#1A1820",
            "foreground": "#F4EFFA",
            "accent": "#C4B5FD",
            "font_scale": 1.0,
            "radius_px": 12,
            "spacing_px": 10,
        },
    }


def quota_window_spec(
    *,
    demo: bool = False,
    codex_enabled: bool = False,
    teamsense_enabled: bool = True,
) -> dict[str, Any]:
    if demo:
        title = "模型额度 · 合成演示"
    elif codex_enabled and teamsense_enabled:
        title = "模型额度 · 本机"
    elif codex_enabled:
        title = "Codex 额度 · 本机"
    else:
        title = "模型额度 · TeamSense"
    return {
        "title": title,
        "width": 430,
        "height": 500,
        "always_on_top": True,
        "geometry_control": "human",
        "resizable": True,
        "text_selectable": False,
        "surface_opacity": 0.8,
    }


def synthetic_demo_snapshot(now: datetime | None = None) -> dict[str, Any]:
    """Return obviously synthetic data for visual/scene checks without network access."""
    observed = (now or datetime.now().astimezone()).isoformat(timespec="seconds")
    meta = lambda source: {
        "sourceKey": source,
        "freshness": "fresh",
        "upstreamState": "healthy",
        "fetchedAt": observed,
        "lastSuccessAt": observed,
    }
    return {
        "deepseek": {
            "balance": {
                "fetchedAt": observed,
                "isAvailable": True,
                "balances": [
                    {"currency": "CNY", "totalMicros": 31_250_000,
                     "grantedMicros": 10_000_000, "toppedUpMicros": 21_250_000},
                ],
            },
            "meta": meta("deepseek"),
        },
        "minimax": {
            "quota": {
                "fetchedAt": observed,
                "isAvailable": True,
                "models": [
                    {
                        "key": "synthetic-model-a",
                        "name": "Synthetic Model A",
                        "interval": {
                            "state": "metered", "windowSeconds": 3600,
                            "remainingPercent": 62, "usedCount": None,
                            "remainingCount": None, "totalCount": None, "resetsAt": None,
                        },
                        "weekly": {
                            "state": "metered", "windowSeconds": 604800,
                            "remainingPercent": 24, "usedCount": None,
                            "remainingCount": None, "totalCount": None, "resetsAt": None,
                        },
                    },
                ],
            },
            "meta": meta("minimax"),
        },
        "sub2api": {
            "management": None,
            "meta": {
                **meta("sub2api"),
                "freshness": "empty",
                "upstreamState": "unknown",
                "fetchedAt": None,
                "lastSuccessAt": None,
            },
        },
    }
