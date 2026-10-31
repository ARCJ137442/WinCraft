'''本机模型额度投影与 WinCraft 声明式场景构建器。
- 🎯隔离来源、币种、模型、额度周期与 freshness，不推算未知字段。
- 📌此模块不连接 TeamSense 或供应商服务，也不访问本机凭据。
- 🤖由 Agent 编写，未经人工逐行审阅。
'''
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

MAX_MODELS = 8
MAX_BALANCES = 4
MAX_SAFE_INTEGER = 9_007_199_254_740_991

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


def __mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def __safe_text(value: Any, fallback: str = "") -> str:
    if not isinstance(value, str):
        return fallback
    normalized = " ".join("".join(char for char in value if char.isprintable()).split())
    return normalized[:80] or fallback


def __safe_timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value


def __source_meta(raw: Any) -> dict[str, str]:
    meta = __mapping(raw)
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
    source_error = meta.get("errorCode")
    error_labels = {
        "NOT_ENABLED": "来源未启用",
        "NOT_CONFIGURED": "本机密钥未配置",
        "AUTH_REJECTED": "供应商未接受本机密钥",
        "REDIRECT_BLOCKED": "已拒绝非预期重定向",
        "UPSTREAM_REJECTED": "供应商拒绝额度读取",
        "REQUEST_TIMEOUT": "供应商请求超时",
        "NETWORK_ERROR": "供应商网络读取失败",
        "RESPONSE_TOO_LARGE": "供应商响应超过本机上限",
        "INVALID_JSON": "供应商响应不是有效 JSON",
        "INVALID_RESPONSE": "供应商响应结构无效",
    }
    if isinstance(source_error, str) and source_error in error_labels:
        upstream_label = error_labels[source_error]
        upstream_tone = "muted" if source_error in {"NOT_ENABLED", "NOT_CONFIGURED"} else "danger"
    fetched_at = __safe_timestamp(meta.get("fetchedAt"))
    return {
        "freshness_label": freshness_label,
        "freshness_tone": freshness_tone,
        "upstream_label": upstream_label,
        "upstream_tone": upstream_tone,
        "updated_at": f"缓存更新时间：{fetched_at}" if fetched_at else "缓存更新时间未知",
    }


def __valid_non_negative_integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or value > MAX_SAFE_INTEGER:
        return None
    return value


def __currency_display(currency: str, micros: int) -> str:
    amount = (Decimal(micros) / Decimal(1_000_000)).quantize(Decimal("0.01"))
    symbol = "¥" if currency == "CNY" else "$"
    return f"{symbol}{amount:,.2f}"


def __deepseek_balances(raw_balance: Any) -> tuple[str, list[dict[str, str]]]:
    balance = __mapping(raw_balance)
    available = balance.get("isAvailable")
    if available is not True:
        return ("余额来源不可用" if available is False else "余额状态未知"), []
    raw_items = balance.get("balances")
    if not isinstance(raw_items, list):
        return "余额数据未知", []
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_items:
        record = __mapping(item)
        currency = record.get("currency")
        amount = __valid_non_negative_integer(record.get("totalMicros"))
        if (
            not isinstance(currency, str)
            or currency not in {"CNY", "USD"}
            or amount is None
            or currency in seen
        ):
            continue
        seen.add(currency)
        items.append(
            {"currency": currency, "display": __currency_display(currency, amount)}
        )
        if len(items) >= MAX_BALANCES:
            break
    return ("余额快照" if items else "余额字段缺失或无效"), items


def __quota_window(model_name: str, window: str, raw: Any) -> dict[str, Any]:
    record = __mapping(raw)
    state = record.get("state")
    if not isinstance(state, str):
        state = None
    status_label = WINDOW_STATE_LABELS.get(state, "额度未知")
    remaining_percent = record.get("remainingPercent")
    remaining_count = __valid_non_negative_integer(record.get("remainingCount"))
    total_count = __valid_non_negative_integer(record.get("totalCount"))
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
    elif (
        remaining_count is not None
        and total_count is not None
        and total_count > 0
        and remaining_count <= total_count
    ):
        value = remaining_count
        maximum = total_count
        detail = f"剩余 {remaining_count:,} / {total_count:,} 次"
    else:
        status_label = "额度未知"
        detail = status_label
    reset_at = __safe_timestamp(record.get("resetsAt"))
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


def __minimax_windows(raw_quota: Any) -> tuple[str, list[dict[str, Any]], int]:
    quota = __mapping(raw_quota)
    available = quota.get("isAvailable")
    if available is not True:
        return ("额度来源不可用" if available is False else "额度状态未知"), [], 0
    models = quota.get("models")
    if not isinstance(models, list):
        return "额度数据未知", [], 0
    windows: list[dict[str, Any]] = []
    omitted_models = max(0, len(models) - MAX_MODELS)
    reported_omissions = __valid_non_negative_integer(quota.get("omittedModelCount"))
    if reported_omissions is not None:
        omitted_models = max(omitted_models, reported_omissions)
    for model in models[:MAX_MODELS]:
        record = __mapping(model)
        name = __safe_text(record.get("name"), "未命名模型")
        windows.append(__quota_window(name, "当前周期", record.get("interval")))
        windows.append(__quota_window(name, "周周期", record.get("weekly")))
    return ("模型周期额度" if windows else "没有可显示的模型额度"), windows, omitted_models


def __collector_read_state(
    *,
    enabled_sources: list[str],
    observed_at: str | None,
    demo: bool,
) -> dict[str, str | None]:
    safe_observed_at = __safe_timestamp(observed_at)
    if demo:
        state_label, tone = "合成演示数据", "accent"
        detail = "无凭据读取 · 无网络请求 · 合成数据"
    elif enabled_sources:
        state_label, tone = "本机额度来源已启用", "success"
        detail = "来源分别读取 · 不调用 TeamSense API"
    else:
        state_label, tone = "没有启用额度来源", "muted"
        detail = "启用来源后才读取本机 rollout 或固定的供应商只读 HTTPS 接口"
    return {
        "state_label": state_label,
        "state_tone": tone,
        "observed_at": f"面板更新：{safe_observed_at}" if safe_observed_at else "面板更新时间未知",
        "detail": detail,
        "error_code": None,
    }


def normalize_quota_snapshot(
    payload: Any,
    *,
    observed_at: str | None = None,
    enabled_sources: list[str] | None = None,
    demo: bool = False,
) -> dict[str, Any]:
    """只投影有限展示字段；不推断账号、额度或缺失值。"""
    if not isinstance(payload, Mapping):
        payload = {}
    deepseek = __mapping(payload.get("deepseek"))
    minimax = __mapping(payload.get("minimax"))
    deepseek_state, balances = __deepseek_balances(deepseek.get("balance"))
    minimax_state, windows, omitted_models = __minimax_windows(minimax.get("quota"))
    deepseek_meta = __source_meta(deepseek.get("meta"))
    minimax_meta = __source_meta(minimax.get("meta"))
    deepseek_error = __mapping(deepseek.get("meta")).get("errorCode")
    minimax_error = __mapping(minimax.get("meta")).get("errorCode")
    if isinstance(deepseek_error, str) and deepseek_error in {"NOT_ENABLED", "NOT_CONFIGURED"}:
        deepseek_state = deepseek_meta["upstream_label"]
    if isinstance(minimax_error, str) and minimax_error in {"NOT_ENABLED", "NOT_CONFIGURED"}:
        minimax_state = minimax_meta["upstream_label"]
    safe_sources = [
        source
        for source in enabled_sources or []
        if source in {"codex_rollout", "codex_live", "deepseek_balance", "minimax_quota"}
    ]
    return {
        "collector": __collector_read_state(
            enabled_sources=safe_sources,
            observed_at=observed_at,
            demo=demo,
        ),
        "identity_scope": "本机各来源独立；账户标识与 API key 不进入悬浮窗",
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
        "codex": {
            "state_label": "未启用",
            "state_tone": "muted",
            "freshness_label": "尚未读取",
            "freshness_tone": "muted",
            "observed_at": None,
            "observed_label": "尚无成功读取时间",
            "detail": "Codex quota 来源未启用；不会读取 Codex App 或访问网络。",
            "windows": [],
        },
        "sources": safe_sources,
    }


def __node(
    node_id: str,
    kind: str,
    props: dict[str, Any] | None = None,
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {"id": node_id, "kind": kind, "props": props or {}, "children": children or []}


def __bound(path: str) -> dict[str, str]:
    return {"$path": path}


def build_quota_scene(projection: Mapping[str, Any]) -> dict[str, Any]:
    """Build a compact dashboard; model and quota-window identity stay visible."""
    data = dict(projection)
    deepseek = __mapping(data.get("deepseek"))
    minimax = __mapping(data.get("minimax"))
    codex = __mapping(data.get("codex"))
    deepseek_balances = (
        deepseek.get("balances") if isinstance(deepseek.get("balances"), list) else []
    )
    deepseek_children = [
        __node(
            f"quota-deepseek-balance-{index}",
            "metric",
            {
                "label": f"DeepSeek · {item['currency']} 余额",
                "value": __bound(f"/deepseek/balances/{index}/display"),
                "caption": "余额，不代表订阅总额度",
            },
        )
        for index, item in enumerate(deepseek_balances)
        if isinstance(item, Mapping)
    ]
    if not deepseek_children:
        deepseek_children.append(
            __node(
                "quota-deepseek-empty",
                "text",
                {"text": __bound("/deepseek/state_label"), "size": "small"},
            )
        )

    minimax_windows = (
        minimax.get("windows") if isinstance(minimax.get("windows"), list) else []
    )
    minimax_children: list[dict[str, Any]] = []
    for index, item in enumerate(minimax_windows):
        if not isinstance(item, Mapping):
            continue
        if (
            isinstance(item.get("value"), (int, float))
            and isinstance(item.get("maximum"), (int, float))
        ):
            minimax_children.append(
                __node(
                    f"quota-minimax-window-{index}",
                    "progress",
                    {
                        "label": __bound(f"/minimax/windows/{index}/label"),
                        "value": __bound(f"/minimax/windows/{index}/value"),
                        "max": __bound(f"/minimax/windows/{index}/maximum"),
                    },
                )
            )
            minimax_children.append(
                __node(
                    f"quota-minimax-detail-{index}",
                    "text",
                    {"text": __bound(f"/minimax/windows/{index}/detail"), "size": "small"},
                )
            )
        else:
            minimax_children.append(
                __node(
                    f"quota-minimax-window-{index}",
                    "text",
                    {"text": __bound(f"/minimax/windows/{index}/detail"), "size": "small"},
                )
            )
    if not minimax_children:
        minimax_children.append(
            __node(
                "quota-minimax-empty",
                "text",
                {"text": __bound("/minimax/state_label"), "size": "small"},
            )
        )
    if minimax.get("omitted_model_count", 0) > 0:
        minimax_children.append(
            __node(
                "quota-minimax-omitted-models",
                "text",
                {"text": __bound("/minimax/omitted_models_label"), "size": "small"},
            )
        )

    codex_windows = codex.get("windows") if isinstance(codex.get("windows"), list) else []
    codex_children: list[dict[str, Any]] = []
    for index, item in enumerate(codex_windows[:2]):
        if not isinstance(item, Mapping):
            continue
        if (
            isinstance(item.get("value"), (int, float))
            and isinstance(item.get("maximum"), (int, float))
        ):
            codex_children.append(
                __node(
                    f"quota-codex-window-{index}",
                    "progress",
                    {
                        "label": __bound(f"/codex/windows/{index}/label"),
                        "value": __bound(f"/codex/windows/{index}/value"),
                        "max": __bound(f"/codex/windows/{index}/maximum"),
                    },
                )
            )
            codex_children.append(
                __node(
                    f"quota-codex-detail-{index}",
                    "text",
                    {"text": __bound(f"/codex/windows/{index}/detail"), "size": "small"},
                )
            )
    if not codex_children:
        codex_children.append(
            __node(
                "quota-codex-empty",
                "text",
                {"text": __bound("/codex/detail"), "size": "small"},
            )
        )

    root = __node(
        "quota-panel-root",
        "stack",
        {"gap": 10},
        [
            __node(
                "quota-panel-heading",
                "row",
                {"gap": 10},
                [
                    __node("quota-panel-title", "text", {"text": "模型额度", "size": "title"}),
                    __node(
                        "quota-collector-state",
                        "badge",
                        {
                            "text": __bound("/collector/state_label"),
                            "tone": __bound("/collector/state_tone"),
                        },
                    ),
                ],
            ),
            __node(
                "quota-collector-observed-at",
                "text",
                {"text": __bound("/collector/observed_at"), "size": "small"},
            ),
            __node(
                "quota-collector-detail",
                "text",
                {"text": __bound("/collector/detail"), "size": "small"},
            ),
            __node(
                "quota-identity-scope",
                "text",
                {"text": __bound("/identity_scope"), "size": "small"},
            ),
            __node("quota-divider-primary", "divider"),
            __node(
                "quota-deepseek",
                "stack",
                {"gap": 6},
                [
                    __node(
                        "quota-deepseek-heading",
                        "row",
                        {"gap": 8},
                        [
                            __node(
                                "quota-deepseek-title",
                                "text",
                                {"text": "DeepSeek", "size": "heading"},
                            ),
                            __node(
                                "quota-deepseek-freshness",
                                "badge",
                                {
                                    "text": __bound("/deepseek/freshness_label"),
                                    "tone": __bound("/deepseek/freshness_tone"),
                                },
                            ),
                        ],
                    ),
                    __node(
                        "quota-deepseek-source-state",
                        "text",
                        {
                            "text": __bound("/deepseek/upstream_label"),
                            "size": "small",
                        },
                    ),
                    __node(
                        "quota-deepseek-balances",
                        "row",
                        {"gap": 10},
                        deepseek_children,
                    ),
                    __node(
                        "quota-deepseek-updated",
                        "text",
                        {"text": __bound("/deepseek/updated_at"), "size": "small"},
                    ),
                ],
            ),
            __node("quota-divider-secondary", "divider"),
            __node(
                "quota-minimax",
                "stack",
                {"gap": 6},
                [
                    __node(
                        "quota-minimax-heading",
                        "row",
                        {"gap": 8},
                        [
                            __node(
                                "quota-minimax-title",
                                "text",
                                {"text": "MiniMax", "size": "heading"},
                            ),
                            __node(
                                "quota-minimax-freshness",
                                "badge",
                                {
                                    "text": __bound("/minimax/freshness_label"),
                                    "tone": __bound("/minimax/freshness_tone"),
                                },
                            ),
                        ],
                    ),
                    __node(
                        "quota-minimax-source-state",
                        "text",
                        {"text": __bound("/minimax/upstream_label"), "size": "small"},
                    ),
                    __node(
                        "quota-minimax-windows",
                        "stack",
                        {"gap": 5},
                        minimax_children,
                    ),
                    __node(
                        "quota-minimax-updated",
                        "text",
                        {"text": __bound("/minimax/updated_at"), "size": "small"},
                    ),
                ],
            ),
            __node("quota-divider-tertiary", "divider"),
            __node(
                "quota-codex",
                "stack",
                {"gap": 5},
                [
                    __node(
                        "quota-codex-heading",
                        "row",
                        {"gap": 8},
                        [
                            __node(
                                "quota-codex-title",
                                "text",
                                {"text": "Codex", "size": "heading"},
                            ),
                            __node(
                                "quota-codex-state",
                                "badge",
                                {
                                    "text": __bound("/codex/state_label"),
                                    "tone": __bound("/codex/state_tone"),
                                },
                            ),
                        ],
                    ),
                    __node(
                        "quota-codex-freshness",
                        "text",
                        {"text": __bound("/codex/observed_label"), "size": "small"},
                    ),
                    *codex_children,
                    __node(
                        "quota-codex-source-note",
                        "text",
                        {"text": __bound("/codex/detail"), "size": "small"},
                    ),
                ],
            ),
            __node(
                "quota-panel-footer",
                "text",
                {
                    "text": (
                        "各来源、币种与额度周期独立显示；Codex 使用本机只读来源。"
                    ),
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
    deepseek_enabled: bool = False,
    minimax_enabled: bool = False,
) -> dict[str, Any]:
    if demo:
        title = "模型额度 · 合成演示"
    elif sum((codex_enabled, deepseek_enabled, minimax_enabled)) > 1:
        title = "模型额度 · 本机"
    elif codex_enabled:
        title = "Codex 额度 · 本机"
    elif deepseek_enabled:
        title = "DeepSeek 额度 · 本机"
    elif minimax_enabled:
        title = "MiniMax 额度 · 本机"
    else:
        title = "模型额度 · 本机"
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
    }
