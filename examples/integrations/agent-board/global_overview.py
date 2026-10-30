"""Compact one-window navigation over explicitly selected activity sources."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Mapping

from activity_board import aggregate_activities, load_synthetic_activities

MAX_VISIBLE_SESSIONS = 4
MAX_CLAUDE_PREVIEW_SESSIONS = 3
MAX_CODEX_APP_PREVIEW_SESSIONS = 2
MAX_CODEX_CLI_PREVIEW_SESSIONS = 2
SUMMARY_PREVIEW_CHARS = 72
SOURCE_IDS = {"Codex": "codex", "Codex App": "codex-app", "Claude Code": "claude-code"}
SOURCE_LABELS = {value: key for key, value in SOURCE_IDS.items()}
SOURCE_HEALTH_LABELS = {
    "online": "在线",
    "offline": "进程离线",
    "partial": "部分可用",
    "disconnected": "断开",
    "unavailable": "不可用",
    "not_requested": "本轮未查询",
    "synthetic": "合成",
    "local_state": "本机状态库",
    "unknown": "未知",
}
'''📜来源健康状态的固定显示词汇'''
SOURCE_HEALTH_TONES = {
    "online": "accent",
    "offline": "muted",
    "partial": "warning",
    "disconnected": "danger",
    "unavailable": "danger",
    "not_requested": "muted",
    "synthetic": "muted",
    "local_state": "muted",
    "unknown": "muted",
}
'''📜来源健康状态与通用 renderer tone 的固定映射'''
SOURCE_DATA_HEALTH_LABELS = {
    "local_state": "本机数据可读",
    "partial": "部分读取",
    "unavailable": "数据不可用",
    "disconnected": "读取失败",
    "not_requested": "本轮未查询",
    "not_applicable": "实时状态来源",
    "unknown": "数据状态未知",
}
SOURCE_DATA_HEALTH_TONES = {
    "local_state": "success",
    "partial": "warning",
    "unavailable": "danger",
    "disconnected": "danger",
    "not_requested": "muted",
    "not_applicable": "muted",
    "unknown": "muted",
}


@dataclass(frozen=True)
class DetailTarget:
    identity: tuple[str, str, str, str]
    source_id: str
    source_label: str
    display_name: str
    project_label: str
    observed_at: str
    relation: str


@dataclass(frozen=True)
class GlobalOverviewState:
    source: str = "all"
    selected_identity: tuple[str, str, str, str] | None = None
    page: int = 0
    revision: int = 0
    selected_target: DetailTarget | None = None
    selection_missing: bool = False


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
    '''Retain a selected identity across snapshots without claiming why it disappeared'''
    if state.selected_identity is None:
        return state
    sessions = {
        tuple(session['identity']): session
        for session in projection['sessions']
    }
    selected = sessions.get(tuple(state.selected_identity))
    if selected is None:
        if state.selection_missing:
            return state
        return replace(state, selection_missing=True, revision=state.revision + 1)

    target = _detail_target(selected, projection.get('source_labels', SOURCE_LABELS))
    if state.selection_missing:
        return replace(
            state,
            selected_target=target,
            selection_missing=False,
            revision=state.revision + 1,
        )
    if state.selected_target != target:
        return replace(state, selected_target=target)
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
        "unknown": sum(
            session["normalized_status"] in {"unknown", "not_loaded"}
            for session in leaves
        ),
    }


def _known_running_count(sessions: list[dict[str, Any]], health: str) -> int | str:
    if health not in {"online", "partial", "synthetic"}:
        return "—"
    leaves = [session for session in sessions if session["is_leaf"]]
    if any(session["normalized_status"] in {"unknown", "not_loaded"} for session in leaves):
        return "—"
    return sum(session["normalized_status"] == "running" for session in leaves)


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
            "online": "进程在线",
            "offline": "进程离线",
            "partial": "部分数据",
            "disconnected": "进程状态读取中断",
            "unavailable": "进程状态不可用",
            "not_requested": "本轮未查询",
            "local_state": "本机状态库可读",
        }.get(health, SOURCE_HEALTH_LABELS.get(health, "未知"))
    if source_id in {"codex", "claude-code"}:
        return {
            "online": "CLI 可查询",
            "partial": "CLI 部分可用",
            "disconnected": "CLI 查询失败",
            "unavailable": "CLI 未就绪",
            "not_requested": "本轮未查询",
        }.get(health, SOURCE_HEALTH_LABELS.get(health, "未知"))
    return SOURCE_HEALTH_LABELS.get(health, "未知")


def _source_update_label(source_id: str, projection: Mapping[str, Any]) -> str:
    '''显示来源上次成功读取年龄，不将连接状态冒充为内容新鲜度'''
    if projection.get("data_mode_label") == "合成":
        return "合成数据"
    if projection.get("source_health", {}).get(source_id) == "not_requested":
        return "本轮未查询"
    freshness = projection.get("source_freshness", {}).get(source_id)
    age = projection.get("source_age_seconds", {}).get(source_id)
    if age is None:
        if freshness == "disconnected":
            return "断开 · 尚无成功读取"
        if freshness == "unavailable" and source_id == "codex-app":
            return "尚未读取到本机状态"
        return "尚无成功读取"
    if freshness == "disconnected":
        return f"断开 · 上次成功 {age} 秒前"
    if freshness == "stale":
        return f"已过期 · 上次成功 {age} 秒前"
    if freshness == "fresh":
        return f"刚刚读取（{age} 秒前）" if age < 5 else f"读取于 {age} 秒前"
    return "采样时间未知"


def _session_output_label(session: Mapping[str, Any]) -> str:
    '''按来源契约说明最近文本的性质，不把通用预览冒充 Agent 发言'''
    output_kind = str(session.get("last_output_kind", "unavailable"))
    if output_kind == "unavailable":
        return "暂无最近 Agent 输出"
    return {
        "agent_message": "最近 Agent 输出",
        "connector_summary": "最近活动摘要",
        "source_preview": "会话预览（发言方未标注）",
    }.get(output_kind, "最近活动摘要")


def _session_output_value(session: Mapping[str, Any]) -> str:
    label = _session_output_label(session)
    output = _summary_preview(session.get("summary", ""))
    return f"{label}：{output}" if output else label


def _session_project_value(session: Mapping[str, Any]) -> str:
    project = str(session.get("project_label") or "").strip()
    return f"项目：{project}" if project else "项目：来源未提供"


def _detail_target(
    session: Mapping[str, Any],
    source_labels: Mapping[str, str],
) -> DetailTarget:
    source_type = str(session.get("source_type_label", ""))
    source_id = SOURCE_IDS.get(source_type)
    if source_id is None:
        raise ValueError("selected session has an unknown source type")
    relation = "child session" if session.get("has_parent") else "top-level session"
    return DetailTarget(
        identity=tuple(session["identity"]),
        source_id=source_id,
        source_label=str(source_labels.get(source_id, source_type)),
        display_name=str(session.get("display_name") or "会话")[:128],
        project_label=str(session.get("project_label") or "").strip()[:128],
        observed_at=str(session.get("observed_at") or "")[:64],
        relation=relation,
    )


def _register_detail_targets(
    targets: dict[str, DetailTarget],
    session: Mapping[str, Any],
    source_labels: Mapping[str, str],
    *component_ids: str,
) -> None:
    target = _detail_target(session, source_labels)
    for component_id in component_ids:
        targets[component_id] = target


def _source_freshness_tone(source_id: str, projection: Mapping[str, Any]) -> str:
    freshness = projection.get("source_freshness", {}).get(source_id)
    return "danger" if freshness in {"stale", "disconnected", "unavailable"} else "muted"


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
) -> tuple[dict[str, Any], dict[str, DetailTarget], int]:
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
    source_data_health = projection.get("source_data_health", {})
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

    selected = None
    if state.selected_identity is not None:
        selected = next(
            (
                session for session in projection["sessions"]
                if tuple(session["identity"]) == tuple(state.selected_identity)
            ),
            None,
        )
    current_source = state.source
    if selected is not None:
        current_source = SOURCE_IDS.get(selected["source_type_label"], "all")
    elif state.selected_target is not None:
        current_source = state.selected_target.source_id

    visible = (
        sources.get(current_source, [])
        if current_source != "all"
        else []
    )
    page_count = max(1, (len(visible) + page_size - 1) // page_size)
    page = min(max(state.page, 0), page_count - 1)
    start = page * page_size
    page_sessions = visible[start : start + page_size]
    detail_targets: dict[str, DetailTarget] = {}

    codex_app_summary = source_summaries["codex-app"]
    claude_summary = source_summaries["claude-code"]
    is_live = projection.get("data_mode_label") != "合成"
    primary_codex_source = "codex-app" if is_live else "codex"
    primary_codex_health = source_health.get(primary_codex_source, "unknown")
    primary_codex_count = _known_running_count(
        sources[primary_codex_source],
        str(primary_codex_health),
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
                _known_running_count(sources["codex"], str(source_health.get("codex", "unknown")))
            ),
            "codex_app_sessions": codex_app_summary["sessions"],
            "codex_app_running": codex_app_summary["running"],
            "codex_app_blocked": codex_app_summary["blocked"],
            "codex_app_stale": codex_app_summary["stale"],
            "codex_app_health": health_labels["codex-app"],
            "codex_app_health_tone": health_tones["codex-app"],
            "codex_app_data_health": SOURCE_DATA_HEALTH_LABELS.get(
                str(source_data_health.get("codex-app", "not_requested")), "未知"
            ),
            "codex_app_data_health_tone": SOURCE_DATA_HEALTH_TONES.get(
                str(source_data_health.get("codex-app", "not_requested")), "muted"
            ),
            "claude_sessions": claude_summary["sessions"],
            "claude_metric_label": f"{source_labels['claude-code']} 后台 Agent",
            "claude_running": claude_summary["running"],
            "claude_waiting": claude_summary["waiting"],
            "claude_blocked": claude_summary["blocked"],
            "claude_stale": claude_summary["stale"],
            "claude_health": health_labels["claude-code"],
            "claude_health_tone": health_tones["claude-code"],
            "claude_data_health": SOURCE_DATA_HEALTH_LABELS.get(
                str(source_data_health.get("claude-code", "not_requested")), "未知"
            ),
            "claude_data_health_tone": SOURCE_DATA_HEALTH_TONES.get(
                str(source_data_health.get("claude-code", "not_requested")), "muted"
            ),
            "codex_cli_updated": _source_update_label("codex", projection),
            "codex_app_updated": _source_update_label("codex-app", projection),
            "claude_updated": _source_update_label("claude-code", projection),
        },
        "codex_cli_preview": [],
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
                            {
                                "id": f"global-{source_id}-data-health",
                                "kind": "badge",
                                "props": {
                                    "text": {"$path": f"/summary/{health_key}_data_health"},
                                    "tone": {"$path": f"/summary/{health_key}_data_health_tone"},
                                },
                                "children": [],
                            }
                        ]
                        if source_id in {"codex-app", "claude-code"}
                        and source_id in source_data_health
                        and source_data_health.get(source_id) != "not_requested"
                        else []
                    ),
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
        if selected is None:
            target = state.selected_target
            source_label = target.source_label if target else str(source_labels.get(current_source, "来源未知"))
            detail = {
                "source": source_label,
                "session": target.display_name if target else "所选会话当前不可见",
                "project": target.project_label if target else "",
                "summary_label": "最近输出暂不可用",
                "summary": "最新快照未返回这条会话；不会据此判定为已撤销。",
                "status": "当前快照未显示",
                "status_tone": "warning",
                "freshness": _source_update_label(current_source, projection),
                "freshness_tone": _source_freshness_tone(current_source, projection),
                "timing": (
                    f"最后可见于 {target.observed_at}"
                    if target and target.observed_at
                    else "最后可见时间未知"
                ),
                "relation": target.relation if target else "会话关系未知",
                "revocation": "撤销状态未知 · 来源未报告",
            }
            session_node = _text("global-detail-session", detail["session"])
        else:
            timing = [f"Observed {selected['observed_at']}"]
            if selected.get("expires_at"):
                timing.append(f"valid until {selected['expires_at']}")
            timing.append("child session" if selected["has_parent"] else "top-level session")
            detail = {
                "source": str(source_labels.get(current_source, selected["source_type_label"])),
                "session": selected["display_name"],
                "project": selected.get("project_label", ""),
                "summary_label": _session_output_label(selected),
                "summary": (
                    _summary_preview(selected["summary"])
                    if selected["source_type_label"] != "Codex App"
                    else str(selected["summary"] or "")[:256]
                ),
                "status": selected["status_label"],
                "status_tone": _status_tone(selected),
                "freshness": selected["freshness_label"],
                "freshness_tone": _freshness_tone(selected),
                "timing": " · ".join(timing),
                "relation": "child session" if selected["has_parent"] else "top-level session",
                "revocation": "撤销状态未知 · 来源未报告",
            }
            session_node = _session_title_node(
                selected,
                "global-detail-session",
                "view.open_detail",
                codex_app_links_enabled=codex_app_links_enabled,
            )
        scene_data["detail"] = detail
        children.extend(
            [
                session_node,
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
                _text("global-detail-revocation", {"$path": "/detail/revocation"}, "small"),
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
            elif source_health.get(source_id) == "offline" and source_id in {"codex-app", "claude-code"}:
                attention.append(f"{source_label} 进程离线；本地历史仍可查看")
        if attention:
            children.append(_text("global-overview-attention", " · ".join(attention), "small"))
        codex_sessions = sources["codex"]
        children.append(_text("global-codex-cli-preview-title", f"{source_labels['codex']} · 会话状态", "heading"))
        if not codex_sessions:
            health = source_health.get("codex", "unknown")
            empty_text = (
                "来源查询失败，当前状态不确定。"
                if health == "disconnected"
                else "当前没有可显示的 Codex CLI 会话。"
            )
            children.append(_text("global-codex-cli-preview-empty", empty_text))
        active_codex_sessions = [
            session for session in codex_sessions
            if session["normalized_status"] in {"running", "waiting_input", "waiting_approval", "blocked"}
        ]
        codex_cli_preview = active_codex_sessions or codex_sessions
        for index, session in enumerate(codex_cli_preview[:MAX_CODEX_CLI_PREVIEW_SESSIONS]):
            button_id = f"global-codex-cli-preview-detail-{state.revision}-{index}"
            _register_detail_targets(detail_targets, session, source_labels, button_id)
            scene_data["codex_cli_preview"].append(
                {
                    "name": session["display_name"],
                    "status": session["status_label"],
                    "freshness": session["freshness_label"],
                    "project": _session_project_value(session),
                    "output": _session_output_value(session),
                }
            )
            preview_children = [
                {
                    "id": f"global-codex-cli-preview-heading-{state.revision}-{index}",
                    "kind": "row",
                    "props": {"gap": 8},
                    "children": [
                        _text(
                            f"global-codex-cli-preview-name-{state.revision}-{index}",
                            {"$path": f"/codex_cli_preview/{index}/name"},
                        ),
                        {
                            "id": f"global-codex-cli-preview-status-{state.revision}-{index}",
                            "kind": "badge",
                            "props": {
                                "text": {"$path": f"/codex_cli_preview/{index}/status"},
                                "tone": _status_tone(session),
                            },
                            "children": [],
                        },
                    ],
                },
                _text(
                    f"global-codex-cli-preview-project-{state.revision}-{index}",
                    {"$path": f"/codex_cli_preview/{index}/project"},
                    "small",
                ),
                _text(
                    f"global-codex-cli-preview-output-{state.revision}-{index}",
                    {"$path": f"/codex_cli_preview/{index}/output"},
                    "small",
                ),
            ]
            if session.get("freshness") != "fresh":
                preview_children.append(
                    _text(
                        f"global-codex-cli-preview-freshness-{state.revision}-{index}",
                        {"$path": f"/codex_cli_preview/{index}/freshness"},
                        "small",
                    )
                )
            preview_children.append(_button(button_id, "详情", "view.open_detail"))
            children.append(
                {
                    "id": f"global-codex-cli-preview-row-{state.revision}-{index}",
                    "kind": "stack",
                    "props": {"gap": 3},
                    "children": preview_children,
                }
            )
        if len(codex_cli_preview) > MAX_CODEX_CLI_PREVIEW_SESSIONS:
            children.append(
                _button(
                    "global-codex-cli-preview-more",
                    f"查看其余 {len(codex_cli_preview) - MAX_CODEX_CLI_PREVIEW_SESSIONS} 个会话",
                    "view.source.codex",
                )
            )
        codex_app_sessions = sources["codex-app"]
        if is_live:
            children.append(_text("global-codex-app-preview-title", "Codex App · 会话状态", "heading"))
            if not codex_app_sessions:
                health = source_health.get("codex-app", "unknown")
                data_health = source_data_health.get("codex-app", "unknown")
                empty_text = (
                    "本机 Codex 状态库不可读，当前无法列出会话。"
                    if data_health in {"unavailable", "disconnected"}
                    else "Codex App 进程离线；本机没有可显示的历史会话。"
                    if health == "offline"
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
                _register_detail_targets(
                    detail_targets,
                    session,
                    source_labels,
                    button_id,
                    title_node_id,
                )
                project_label = str(session.get("project_label") or "未归属项目")
                output = _session_output_value(session)
                scene_data["codex_app_preview"].append(
                    {
                        "status": session["status_label"],
                        "freshness": session["freshness_label"],
                        "project": f"项目：{project_label}",
                        "output": output,
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
            data_health = source_data_health.get("claude-code", "unknown")
            empty_text = (
                "Claude Code 本地会话索引不可读。"
                if data_health in {"unavailable", "disconnected"}
                else "Claude Code 进程离线；本机没有可显示的历史会话。"
                if health == "offline"
                else "当前没有可显示的后台 Agent。"
            )
            children.append(_text("global-claude-preview-empty", empty_text))
        for index, session in enumerate(claude_sessions[:MAX_CLAUDE_PREVIEW_SESSIONS]):
            button_id = f"global-claude-preview-detail-{state.revision}-{index}"
            _register_detail_targets(detail_targets, session, source_labels, button_id)
            scene_data["claude_preview"].append(
                {
                    "name": session["display_name"],
                    "status": session["status_label"],
                    "freshness": session["freshness_label"],
                    "project": _session_project_value(session),
                    "output": _session_output_value(session),
                }
            )
            preview_children = [
                {
                    "id": f"global-claude-preview-heading-{state.revision}-{index}",
                    "kind": "row",
                    "props": {"gap": 8},
                    "children": [
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
                    ],
                },
                _text(
                    f"global-claude-preview-project-{state.revision}-{index}",
                    {"$path": f"/claude_preview/{index}/project"},
                    "small",
                ),
                _text(
                    f"global-claude-preview-output-{state.revision}-{index}",
                    {"$path": f"/claude_preview/{index}/output"},
                    "small",
                ),
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
                    "kind": "stack",
                    "props": {"gap": 3},
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
                f"{summary['waiting']} waiting · {summary['blocked']} blocked · "
                f"{summary['unknown']} status unknown · {summary['stale']} stale",
                "small",
            )
        )
        children.append(
            _text(
                "global-source-freshness",
                f"数据新鲜度：{_source_update_label(current_source, projection)}",
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
            _register_detail_targets(detail_targets, session, source_labels, button_id)
            scene_data["sessions"].append(
                {
                    "name": session["display_name"],
                    "status": session["status_label"],
                    "freshness": session["freshness_label"],
                    "project": _session_project_value(session),
                    "output": _session_output_value(session),
                }
            )
            if current_source == "codex-app":
                title_node_id = f"global-session-name-{state.revision}-{index}"
                _register_detail_targets(detail_targets, session, source_labels, title_node_id)
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
                    {
                        "id": f"global-session-heading-{state.revision}-{index}",
                        "kind": "row",
                        "props": {"gap": 8},
                        "children": [
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
                    *(
                        [
                            _text(
                                f"global-session-freshness-{state.revision}-{index}",
                                {"$path": f"/sessions/{index}/freshness"},
                                "small",
                            )
                        ]
                        if session.get("freshness") != "fresh"
                        else []
                    ),
                    _button(button_id, "详情", "view.open_detail"),
                ]
                row_kind = "stack"
                row_props = {"gap": 4}
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
    detail_targets: Mapping[str, DetailTarget],
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
        target = detail_targets.get(component_id)
        if target is None:
            raise ValueError("detail action does not belong to the current rendered view")
        return GlobalOverviewState(
            state.source,
            target.identity,
            state.page,
            revision,
            selected_target=target,
        )
    if action == "view.back":
        return GlobalOverviewState(state.source, None, state.page, revision)
    if action == "view.page.next":
        return GlobalOverviewState(state.source, None, min(state.page + 1, page_count - 1), revision)
    if action == "view.page.previous":
        return GlobalOverviewState(state.source, None, max(state.page - 1, 0), revision)
    raise ValueError("unknown local overview navigation action")
