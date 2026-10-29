"""Compact one-window navigation over explicitly selected activity sources."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Mapping

from activity_board import aggregate_activities, load_synthetic_activities

MAX_VISIBLE_SESSIONS = 4
MAX_CLAUDE_PREVIEW_SESSIONS = 3
MAX_CODEX_APP_PREVIEW_SESSIONS = 2
SUMMARY_PREVIEW_CHARS = 72
SOURCE_IDS = {"Codex": "codex", "Codex App": "codex-app", "Claude Code": "claude-code"}
SOURCE_LABELS = {value: key for key, value in SOURCE_IDS.items()}
SOURCE_HEALTH_LABELS = {
    "online": "在线",
    "partial": "部分可用",
    "disconnected": "断开",
    "unavailable": "不可用",
    "synthetic": "合成",
    "unknown": "未知",
}
'''📜来源健康状态的固定显示词汇'''
SOURCE_HEALTH_TONES = {
    "online": "accent",
    "partial": "warning",
    "disconnected": "danger",
    "unavailable": "danger",
    "synthetic": "muted",
    "unknown": "muted",
}
'''📜来源健康状态与通用 renderer tone 的固定映射'''


@dataclass(frozen=True)
class GlobalOverviewState:
    source: str = "all"
    selected_identity: tuple[str, str, str, str] | None = None
    page: int = 0
    revision: int = 0


def load_synthetic_global_projection(*, now: datetime | None = None) -> dict[str, Any]:
    """Return a repository-owned sample projection; it does not inspect local sessions."""
    projection = aggregate_activities(load_synthetic_activities(), now=now)
    projection['source_health'] = {
        'codex': 'synthetic',
        'codex-app': 'unavailable',
        'claude-code': 'synthetic',
    }
    projection['source_labels'] = SOURCE_LABELS
    projection['data_mode_label'] = '合成'
    return projection


def reconcile_view_state(
    projection: Mapping[str, Any],
    state: GlobalOverviewState,
) -> GlobalOverviewState:
    '''Drop a detail selection when its source session disappears'''
    identities = {tuple(session['identity']) for session in projection['sessions']}
    if state.selected_identity is not None and tuple(state.selected_identity) not in identities:
        return replace(state, selected_identity=None, page=0, revision=state.revision + 1)
    return state


def _source_sessions(projection: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result = {source_id: [] for source_id in SOURCE_LABELS}
    for session in projection["sessions"]:
        source_id = SOURCE_IDS.get(session["source_type_label"])
        if source_id is not None:
            result[source_id].append(session)
    return result


def _source_summary(sessions: list[dict[str, Any]]) -> dict[str, int]:
    leaves = [session for session in sessions if session["is_leaf"]]
    return {
        "sessions": len(sessions),
        "running": sum(session["normalized_status"] == "running" for session in leaves),
        "waiting": sum(
            session["normalized_status"] in {"waiting_input", "waiting_approval"}
            for session in leaves
        ),
        "blocked": sum(session["normalized_status"] == "blocked" for session in leaves),
        "stale": sum(session["normalized_status"] == "stale" for session in leaves),
    }


def _summary_preview(value: Any) -> str:
    summary = " ".join(str(value or "").split())
    if len(summary) <= SUMMARY_PREVIEW_CHARS:
        return summary
    return summary[: SUMMARY_PREVIEW_CHARS - 1].rstrip() + "…"


def _status_tone(session: Mapping[str, Any]) -> str:
    status = session.get("normalized_status")
    if status == "running":
        return "accent"
    if status in {"waiting_input", "waiting_approval"}:
        return "warning"
    if status == "blocked":
        return "danger"
    if status == "stale" or session.get("freshness") in {"stale", "disconnected"}:
        return "danger"
    return "muted"


def _freshness_tone(session: Mapping[str, Any]) -> str:
    if session.get("freshness") in {"stale", "disconnected"}:
        return "danger"
    return "muted"


def _source_health_label(source_id: str, health: str) -> str:
    '''把查询能力与正在运行的应用实例区分开来'''
    if source_id == "codex-app":
        return {
            "online": "已桥接",
            "partial": "部分数据",
            "disconnected": "桥接断开",
            "unavailable": "等待 Agent 桥接",
        }.get(health, SOURCE_HEALTH_LABELS.get(health, "未知"))
    if source_id in {"codex", "claude-code"}:
        return {
            "online": "CLI 可查询",
            "partial": "CLI 部分可用",
            "disconnected": "CLI 查询失败",
            "unavailable": "CLI 未就绪",
        }.get(health, SOURCE_HEALTH_LABELS.get(health, "未知"))
    return SOURCE_HEALTH_LABELS.get(health, "未知")


def _source_update_label(source_id: str, projection: Mapping[str, Any]) -> str:
    '''显示来源上次成功读取年龄，不将连接状态冒充为内容新鲜度'''
    if projection.get("data_mode_label") == "合成":
        return "合成数据"
    freshness = projection.get("source_freshness", {}).get(source_id)
    age = projection.get("source_age_seconds", {}).get(source_id)
    if age is None:
        if freshness == "disconnected":
            return "断开 · 尚无成功读取"
        if freshness == "unavailable" and source_id == "codex-app":
            return "尚未收到快照"
        return "尚无成功读取"
    if freshness == "disconnected":
        return f"断开 · 上次成功 {age} 秒前"
    if freshness == "stale":
        return f"已过期 · 上次成功 {age} 秒前"
    if freshness == "fresh":
        return "刚刚更新" if age < 5 else f"更新于 {age} 秒前"
    return "采样时间未知"


def _codex_app_output_label(session: Mapping[str, Any]) -> str:
    '''Disclose whether Codex App output is an exact turn excerpt or connector summary'''
    return {
        "agent_message": "最近 Agent 输出",
        "connector_summary": "最近活动摘要",
        "unavailable": "暂无最近输出",
    }.get(str(session.get("last_output_kind", "unavailable")), "最近活动摘要")


def _text(node_id: str, value: str | dict[str, str], size: str | None = None) -> dict[str, Any]:
    props: dict[str, Any] = {"text": value}
    if size is not None:
        props["size"] = size
    return {"id": node_id, "kind": "text", "props": props, "children": []}


def _button(
    node_id: str,
    label: str,
    action: str,
    *,
    disabled: bool = False,
    appearance: str | None = None,
    native_window_action: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    props: dict[str, Any] = {"label": label, "action": action, "disabled": disabled}
    if appearance is not None:
        props["appearance"] = appearance
    if native_window_action is not None:
        props["native_window_action"] = dict(native_window_action)
    return {
        "id": node_id,
        "kind": "button",
        "props": props,
        "children": [],
    }


def _session_title_node(
    session: Mapping[str, Any],
    node_id: str,
    action: str,
    *,
    codex_app_links_enabled: bool,
) -> dict[str, Any]:
    '''Render a session title as a safe Codex App link only when host capability exists'''
    thread_id = session.get('codex_app_thread_id')
    if session.get('source_type_label') == 'Codex App' and thread_id and codex_app_links_enabled:
        return _button(
            node_id,
            str(session['display_name']),
            action,
            appearance='link',
            native_window_action={
                'application': 'codex_app',
                'operation': 'open_thread',
                'thread_id': str(thread_id),
            },
        )
    return _text(node_id, str(session['display_name']))


def build_global_overview_scene(
    projection: Mapping[str, Any],
    state: GlobalOverviewState,
    *,
    page_size: int = MAX_VISIBLE_SESSIONS,
) -> tuple[dict[str, Any], dict[str, tuple[str, str, str, str]], int]:
    """Render one compact overview, one source list, or one progressive detail view."""
    if page_size < 1:
        raise ValueError("page_size must be positive")
    sources = _source_sessions(projection)
    source_summaries = {key: _source_summary(value) for key, value in sources.items()}
    source_labels = projection.get("source_labels", SOURCE_LABELS)
    codex_app_links_enabled = bool(projection.get('codex_app_links_enabled', False))
    source_health = projection.get(
        "source_health",
        {source_id: "synthetic" for source_id in SOURCE_LABELS},
    )
    health_labels = {
        source_id: _source_health_label(
            source_id,
            str(source_health.get(source_id, "unknown")),
        )
        for source_id in SOURCE_LABELS
    }
    health_tones = {
        source_id: SOURCE_HEALTH_TONES.get(str(source_health.get(source_id, "unknown")), "muted")
        for source_id in SOURCE_LABELS
    }
    if state.source not in {"all", *SOURCE_LABELS}:
        raise ValueError("unknown source filter")
    state = reconcile_view_state(projection, state)

    current_source = state.source
    if state.selected_identity is not None:
        selected = next(
            session for session in projection["sessions"]
            if tuple(session["identity"]) == tuple(state.selected_identity)
        )
        current_source = SOURCE_IDS.get(selected["source_type_label"], "all")

    visible = (
        sources.get(current_source, [])
        if current_source != "all"
        else []
    )
    page_count = max(1, (len(visible) + page_size - 1) // page_size)
    page = min(max(state.page, 0), page_count - 1)
    start = page * page_size
    page_sessions = visible[start : start + page_size]
    detail_targets: dict[str, tuple[str, str, str, str]] = {}

    codex_summary = source_summaries["codex"]
    codex_app_summary = source_summaries["codex-app"]
    claude_summary = source_summaries["claude-code"]
    is_live = projection.get("data_mode_label") != "合成"
    primary_codex_source = "codex-app" if is_live else "codex"
    primary_codex_summary = source_summaries[primary_codex_source]
    primary_codex_health = source_health.get(primary_codex_source, "unknown")
    primary_codex_count: int | str = (
        primary_codex_summary["running"]
        if primary_codex_health in {"online", "partial", "synthetic"}
        else "—"
    )
    scene_data: dict[str, Any] = {
        "summary": {
            "codex_parallel": primary_codex_count,
            "codex_metric_label": (
                "Codex App 活跃会话" if is_live else "Codex 并行推进"
            ),
            "codex_health": health_labels[primary_codex_source],
            "codex_health_tone": health_tones[primary_codex_source],
            "codex_cli_health": health_labels["codex"],
            "codex_cli_health_tone": health_tones["codex"],
            "codex_cli_active": (
                codex_summary["running"]
                if source_health.get("codex", "unknown") in {"online", "partial", "synthetic"}
                else "—"
            ),
            "codex_app_sessions": codex_app_summary["sessions"],
            "codex_app_running": codex_app_summary["running"],
            "codex_app_blocked": codex_app_summary["blocked"],
            "codex_app_stale": codex_app_summary["stale"],
            "codex_app_health": health_labels["codex-app"],
            "codex_app_health_tone": health_tones["codex-app"],
            "claude_sessions": claude_summary["sessions"],
            "claude_metric_label": f"{source_labels['claude-code']} 后台 Agent",
            "claude_running": claude_summary["running"],
            "claude_waiting": claude_summary["waiting"],
            "claude_blocked": claude_summary["blocked"],
            "claude_stale": claude_summary["stale"],
            "claude_health": health_labels["claude-code"],
            "claude_health_tone": health_tones["claude-code"],
            "codex_cli_updated": _source_update_label("codex", projection),
            "codex_app_updated": _source_update_label("codex-app", projection),
            "claude_updated": _source_update_label("claude-code", projection),
        },
        "codex_app_preview": [],
        "claude_preview": [],
        "sessions": [],
        "detail": {},
    }

    health_source_ids = (
        ("codex-app", "codex", "claude-code")
        if is_live
        else ("codex", "claude-code")
    )
    health_children = []
    for source_id in health_source_ids:
        health_key = {
            "codex": "codex_cli",
            "codex-app": "codex_app",
            "claude-code": "claude",
        }[source_id]
        health_children.append(
            {
                "id": f"global-{source_id}-health-group",
                "kind": "row",
                "props": {"gap": 4},
                "children": [
                    _text(f"global-{source_id}-health-label", str(source_labels[source_id]), "small"),
                    {
                        "id": f"global-{source_id}-health",
                        "kind": "badge",
                        "props": {
                            "text": {"$path": f"/summary/{health_key}_health"},
                            "tone": {"$path": f"/summary/{health_key}_health_tone"},
                        },
                        "children": [],
                    },
                    *(
                        [
                            _text(
                                f"global-{source_id}-freshness",
                                {"$path": f"/summary/{health_key}_updated"},
                                "small",
                            )
                        ]
                        if is_live
                        else []
                    ),
                ],
            }
        )

    children: list[dict[str, Any]] = [
        {
            "id": "global-overview-heading",
            "kind": "row",
            "props": {"gap": 8},
            "children": [
                _text("global-overview-title", "Agent Activity · 全局纵览", "title"),
                {
                    "id": "global-overview-data-mode",
                    "kind": "badge",
                    "props": {"text": str(projection.get("data_mode_label", "合成"))},
                    "children": [],
                },
            ],
        },
        {
            "id": "global-overview-source-health",
            "kind": "row",
            "props": {"gap": 10},
            "children": health_children,
        },
        *(
            [
                _text(
                    "global-codex-cli-health-summary",
                    f"{source_labels['codex']} 活跃任务 · {scene_data['summary']['codex_cli_active']}",
                    "small",
                )
            ]
            if is_live
            else []
        ),
        {
            "id": "global-overview-key-counts",
            "kind": "row",
            "props": {"gap": 24},
            "children": [
                {
                    "id": "global-codex-metric",
                    "kind": "stack",
                    "props": {"gap": 2},
                    "children": [
                        _text("global-codex-label", {"$path": "/summary/codex_metric_label"}, "small"),
                        _text("global-codex-value", {"$path": "/summary/codex_parallel"}, "heading"),
                    ],
                },
                {
                    "id": "global-claude-metric",
                    "kind": "stack",
                    "props": {"gap": 2},
                    "children": [
                        _text("global-claude-label", {"$path": "/summary/claude_metric_label"}, "small"),
                        _text("global-claude-value", {"$path": "/summary/claude_sessions"}, "heading"),
                    ],
                },
            ],
        },
        {
            "id": "global-overview-source-tabs",
            "kind": "row",
            "props": {"gap": 6},
            "children": [
                _button("view-tab-all", "总览", "view.all", disabled=state.source == "all" and state.selected_identity is None),
                *[
                    _button(
                        f"view-tab-{source_id}",
                        str(source_labels[source_id]),
                        f"view.source.{source_id.replace('-', '_')}",
                        disabled=current_source == source_id,
                    )
                    for source_id in (("codex-app", "codex", "claude-code") if is_live else ("codex", "claude-code"))
                ],
            ],
        },
        {"id": "global-overview-divider", "kind": "divider", "props": {}, "children": []},
    ]

    if state.selected_identity is not None:
        detail = selected
        timing = [f"Observed {detail['observed_at']}"]
        if detail.get("expires_at"):
            timing.append(f"valid until {detail['expires_at']}")
        timing.append("child session" if detail["has_parent"] else "top-level session")
        scene_data["detail"] = {
            "source": str(source_labels.get(current_source, detail["source_type_label"])),
            "session": detail["display_name"],
            "project": detail.get("project_label", ""),
            "summary_label": (
                _codex_app_output_label(detail)
                if detail["source_type_label"] == "Codex App"
                else "最近摘要"
            ),
            "summary": (
                _summary_preview(detail["summary"])
                if detail["source_type_label"] != "Codex App"
                else str(detail["summary"] or "")[:256]
            ),
            "status": detail["status_label"],
            "status_tone": _status_tone(detail),
            "freshness": detail["freshness_label"],
            "freshness_tone": _freshness_tone(detail),
            "timing": " · ".join(timing),
            "relation": "child session" if detail["has_parent"] else "top-level session",
        }
        children.extend(
            [
                _session_title_node(
                    detail,
                    "global-detail-session",
                    "view.open_detail",
                    codex_app_links_enabled=codex_app_links_enabled,
                ),
                *(
                    [_text("global-detail-project", {"$path": "/detail/project"}, "small")]
                    if detail.get("project_label")
                    else []
                ),
                _text("global-detail-output-label", {"$path": "/detail/summary_label"}, "small"),
                _text("global-detail-summary", {"$path": "/detail/summary"}, "small"),
                {
                    "id": "global-detail-status-row",
                    "kind": "row",
                    "props": {"gap": 8},
                    "children": [
                        {
                            "id": "global-detail-status",
                            "kind": "badge",
                            "props": {
                                "text": {"$path": "/detail/status"},
                                "tone": {"$path": "/detail/status_tone"},
                            },
                            "children": [],
                        },
                        {
                            "id": "global-detail-freshness",
                            "kind": "badge",
                            "props": {
                                "text": {"$path": "/detail/freshness"},
                                "tone": {"$path": "/detail/freshness_tone"},
                            },
                            "children": [],
                        },
                    ],
                },
                _text("global-detail-timing", {"$path": "/detail/timing"}, "small"),
                _button("global-detail-back", "返回会话列表", "view.back"),
            ]
        )
    elif current_source == "all":
        attention = []
        for source_id, summary in source_summaries.items():
            source_label = source_labels[source_id]
            if summary["waiting"]:
                attention.append(f"{source_label} {summary['waiting']} 等待")
            if summary["blocked"]:
                attention.append(f"{source_label} {summary['blocked']} 阻塞")
            if summary["stale"]:
                attention.append(f"{source_label} {summary['stale']} 陈旧")
        for source_id, source_label in (
            ("codex-app", source_labels["codex-app"]),
            ("codex", source_labels["codex"]),
            ("claude-code", source_labels["claude-code"]),
        ):
            if source_health.get(source_id) == "partial":
                attention.append(f"{source_label} 部分状态未识别")
            elif source_health.get(source_id) == "disconnected":
                attention.append(f"{source_label} 来源断开")
        if attention:
            children.append(_text("global-overview-attention", " · ".join(attention), "small"))
        codex_app_sessions = sources["codex-app"]
        if is_live:
            children.append(_text("global-codex-app-preview-title", "Codex App · 会话状态", "heading"))
            if not codex_app_sessions:
                health = source_health.get("codex-app", "unknown")
                empty_text = (
                    "尚未收到 Codex App 快照；需要 Agent 桥接，应用开着不会自动接入。"
                    if health == "unavailable"
                    else "Codex App 连接失败，当前状态不确定。"
                    if health == "disconnected"
                    else "当前没有可显示的 Codex App 会话。"
                )
                children.append(_text("global-codex-app-preview-empty", empty_text))
            active_sessions = [
                session for session in codex_app_sessions
                if session["normalized_status"] in {"running", "waiting_input", "waiting_approval", "blocked"}
            ]
            codex_app_preview = active_sessions or codex_app_sessions
            for index, session in enumerate(codex_app_preview[:MAX_CODEX_APP_PREVIEW_SESSIONS]):
                button_id = f"global-codex-app-preview-{state.revision}-{index}"
                title_node_id = f"global-codex-app-preview-name-{state.revision}-{index}"
                detail_targets[button_id] = tuple(session["identity"])
                detail_targets[title_node_id] = tuple(session["identity"])
                project_label = str(session.get("project_label") or "未归属项目")
                output_label = _codex_app_output_label(session)
                output = _summary_preview(session.get("summary", "")) or "暂无最近输出"
                scene_data["codex_app_preview"].append(
                    {
                        "status": session["status_label"],
                        "freshness": session["freshness_label"],
                        "project": f"项目：{project_label}",
                        "output": f"{output_label}：{output}",
                    }
                )
                preview_children = [
                    {
                        "id": f"global-codex-app-preview-heading-{state.revision}-{index}",
                        "kind": "row",
                        "props": {"gap": 8},
                        "children": [
                            _session_title_node(
                                session,
                                title_node_id,
                                "view.open_detail",
                                codex_app_links_enabled=codex_app_links_enabled,
                            ),
                            {
                                "id": f"global-codex-app-preview-status-{state.revision}-{index}",
                                "kind": "badge",
                                "props": {
                                    "text": {"$path": f"/codex_app_preview/{index}/status"},
                                    "tone": _status_tone(session),
                                },
                                "children": [],
                            },
                        ],
                    },
                    _text(
                        f"global-codex-app-preview-project-{state.revision}-{index}",
                        {"$path": f"/codex_app_preview/{index}/project"},
                        "small",
                    ),
                    _text(
                        f"global-codex-app-preview-output-{state.revision}-{index}",
                        {"$path": f"/codex_app_preview/{index}/output"},
                        "small",
                    ),
                ]
                if session.get("freshness") != "fresh":
                    preview_children.append(
                        _text(
                            f"global-codex-app-preview-freshness-{state.revision}-{index}",
                            {"$path": f"/codex_app_preview/{index}/freshness"},
                            "small",
                        )
                    )
                if not (session.get("codex_app_thread_id") and codex_app_links_enabled):
                    preview_children.append(_button(button_id, "详情", "view.open_detail"))
                children.append(
                    {
                        "id": f"global-codex-app-preview-row-{state.revision}-{index}",
                        "kind": "stack",
                        "props": {"gap": 3},
                        "children": preview_children,
                    }
                )
            if len(codex_app_preview) > MAX_CODEX_APP_PREVIEW_SESSIONS:
                children.append(
                    _button(
                        "global-codex-app-preview-more",
                        f"查看其余 {len(codex_app_preview) - MAX_CODEX_APP_PREVIEW_SESSIONS} 个会话",
                        "view.source.codex_app",
                    )
                )
        claude_sessions = sources["claude-code"]
        children.append(_text("global-claude-preview-title", f"{source_labels['claude-code']} · 后台 Agent 状态", "heading"))
        if not claude_sessions:
            health = source_health.get("claude-code", "unknown")
            empty_text = (
                "来源连接失败，当前状态不确定。"
                if health == "disconnected"
                else "当前没有可显示的后台 Agent。"
            )
            children.append(_text("global-claude-preview-empty", empty_text))
        for index, session in enumerate(claude_sessions[:MAX_CLAUDE_PREVIEW_SESSIONS]):
            button_id = f"global-claude-preview-detail-{state.revision}-{index}"
            detail_targets[button_id] = tuple(session["identity"])
            scene_data["claude_preview"].append(
                {
                    "name": session["display_name"],
                    "status": session["status_label"],
                    "freshness": session["freshness_label"],
                }
            )
            preview_children = [
                _text(
                    f"global-claude-preview-name-{state.revision}-{index}",
                    {"$path": f"/claude_preview/{index}/name"},
                ),
                {
                    "id": f"global-claude-preview-status-{state.revision}-{index}",
                    "kind": "badge",
                    "props": {
                        "text": {"$path": f"/claude_preview/{index}/status"},
                        "tone": _status_tone(session),
                    },
                    "children": [],
                },
            ]
            if session.get("freshness") != "fresh":
                preview_children.append(
                    _text(
                        f"global-claude-preview-freshness-{state.revision}-{index}",
                        {"$path": f"/claude_preview/{index}/freshness"},
                        "small",
                    )
                )
            preview_children.append(_button(button_id, "详情", "view.open_detail"))
            children.append(
                {
                    "id": f"global-claude-preview-row-{state.revision}-{index}",
                    "kind": "row",
                    "props": {"gap": 8},
                    "children": preview_children,
                }
            )
        if len(claude_sessions) > MAX_CLAUDE_PREVIEW_SESSIONS:
            children.append(
                _button(
                    "global-claude-preview-more",
                    f"查看其余 {len(claude_sessions) - MAX_CLAUDE_PREVIEW_SESSIONS} 个会话",
                    "view.source.claude_code",
                )
            )
    else:
        children.append(_text("global-source-heading", str(source_labels[current_source]), "heading"))
        summary = source_summaries[current_source]
        children.append(
            _text(
                "global-source-summary",
                f"{summary['sessions']} sessions · {summary['running']} running · "
                f"{summary['waiting']} waiting · {summary['blocked']} blocked · {summary['stale']} stale",
                "small",
            )
        )
        if not page_sessions:
            health = source_health.get(current_source, "unknown")
            empty_text = (
                "来源连接失败，当前状态不确定。"
                if health == "disconnected"
                else "该来源当前没有可显示的会话。"
            )
            children.append(_text("global-source-empty", empty_text))
        for index, session in enumerate(page_sessions):
            button_id = f"global-session-detail-{state.revision}-{index}"
            detail_targets[button_id] = tuple(session["identity"])
            project_label = str(session.get("project_label") or "未归属项目")
            output_label = _codex_app_output_label(session)
            output = _summary_preview(session.get("summary", "")) or "暂无最近输出"
            scene_data["sessions"].append(
                {
                    "name": session["display_name"],
                    "status": session["status_label"],
                    "freshness": session["freshness_label"],
                    "project": f"项目：{project_label}" if current_source == "codex-app" else "",
                    "output": f"{output_label}：{output}" if current_source == "codex-app" else "",
                }
            )
            if current_source == "codex-app":
                title_node_id = f"global-session-name-{state.revision}-{index}"
                detail_targets[title_node_id] = tuple(session["identity"])
                session_children = [
                    {
                        "id": f"global-session-heading-{state.revision}-{index}",
                        "kind": "row",
                        "props": {
                            "gap": 8,
                        },
                        "children": [
                            _session_title_node(
                                session,
                                title_node_id,
                                "view.open_detail",
                                codex_app_links_enabled=codex_app_links_enabled,
                            ),
                            {
                                "id": f"global-session-status-{state.revision}-{index}",
                                "kind": "badge",
                                "props": {
                                    "text": {"$path": f"/sessions/{index}/status"},
                                    "tone": _status_tone(session),
                                },
                                "children": [],
                            },
                        ],
                    },
                    _text(
                        f"global-session-project-{state.revision}-{index}",
                        {"$path": f"/sessions/{index}/project"},
                        "small",
                    ),
                    _text(
                        f"global-session-output-{state.revision}-{index}",
                        {"$path": f"/sessions/{index}/output"},
                        "small",
                    ),
                ]
                if session.get("freshness") != "fresh":
                    session_children.append(
                        _text(
                            f"global-session-freshness-{state.revision}-{index}",
                            {"$path": f"/sessions/{index}/freshness"},
                            "small",
                        )
                    )
                if not (session.get("codex_app_thread_id") and codex_app_links_enabled):
                    session_children.append(_button(button_id, "详情", "view.open_detail"))
                row_kind = "stack"
                row_props = {"gap": 4}
            else:
                session_children = [
                    _text(
                        f"global-session-name-{state.revision}-{index}",
                        {"$path": f"/sessions/{index}/name"},
                    ),
                    {
                        "id": f"global-session-status-{state.revision}-{index}",
                        "kind": "badge",
                        "props": {
                            "text": {"$path": f"/sessions/{index}/status"},
                            "tone": _status_tone(session),
                        },
                        "children": [],
                    },
                ]
                if session.get("freshness") != "fresh":
                    session_children.append(
                        _text(
                            f"global-session-freshness-{state.revision}-{index}",
                            {"$path": f"/sessions/{index}/freshness"},
                            "small",
                        )
                    )
                session_children.append(_button(button_id, "详情", "view.open_detail"))
                row_kind = "row"
                row_props = {"gap": 8}
            children.append(
                {
                    "id": f"global-session-row-{state.revision}-{index}",
                    "kind": row_kind,
                    "props": row_props,
                    "children": session_children,
                }
            )
        if page_count > 1:
            children.extend(
                [
                    _text("global-source-page", f"第 {page + 1} / {page_count} 页 · 每页最多 {page_size} 会话"),
                    {
                        "id": "global-source-pagination",
                        "kind": "row",
                        "props": {"gap": 8},
                        "children": [
                            _button("global-page-previous", "上一页", "view.page.previous", disabled=page == 0),
                            _button("global-page-next", "下一页", "view.page.next", disabled=page + 1 >= page_count),
                        ],
                    },
                ]
            )
    children.append(_text("global-overview-footer", "只读状态摘要 · 不批准、不写文件、不继续执行。", "small"))
    return (
        {
            "root": {
                "id": "global-overview-root",
                "kind": "stack",
                "props": {"gap": 6},
                "children": children,
            },
            "data": scene_data,
        },
        detail_targets,
        page_count,
    )


def transition_view(
    state: GlobalOverviewState,
    action: str,
    component_id: str,
    detail_targets: Mapping[str, tuple[str, str, str, str]],
    page_count: int,
) -> GlobalOverviewState:
    """Apply only local navigation actions; no Harness control capability exists here."""
    revision = state.revision + 1
    if action == "view.all":
        return GlobalOverviewState("all", None, 0, revision)
    if action in {"view.source.codex", "view.source.codex_app", "view.source.claude_code"}:
        source = action.removeprefix("view.source.").replace("_", "-")
        return GlobalOverviewState(source, None, 0, revision)
    if action == "view.open_detail":
        identity = detail_targets.get(component_id)
        if identity is None:
            raise ValueError("detail action does not belong to the current rendered view")
        return GlobalOverviewState(state.source, identity, state.page, revision)
    if action == "view.back":
        return GlobalOverviewState(state.source, None, state.page, revision)
    if action == "view.page.next":
        return GlobalOverviewState(state.source, None, min(state.page + 1, page_count - 1), revision)
    if action == "view.page.previous":
        return GlobalOverviewState(state.source, None, max(state.page - 1, 0), revision)
    raise ValueError("unknown local overview navigation action")
