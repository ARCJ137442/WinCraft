"""Compact one-window navigation over explicitly selected activity sources."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Mapping

from activity_board import aggregate_activities, load_synthetic_activities

MAX_VISIBLE_SESSIONS = 4
MAX_CLAUDE_PREVIEW_SESSIONS = 3
SUMMARY_PREVIEW_CHARS = 72
SOURCE_IDS = {"Codex": "codex", "Claude Code": "claude-code"}
SOURCE_LABELS = {value: key for key, value in SOURCE_IDS.items()}


@dataclass(frozen=True)
class GlobalOverviewState:
    source: str = "all"
    selected_identity: tuple[str, str, str, str] | None = None
    page: int = 0
    revision: int = 0


def load_synthetic_global_projection(*, now: datetime | None = None) -> dict[str, Any]:
    """Return a repository-owned sample projection; it does not inspect local sessions."""
    return aggregate_activities(load_synthetic_activities(), now=now)


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
    if status == "stale" or session.get("freshness") in {"stale", "disconnected"}:
        return "danger"
    return "muted"


def _freshness_tone(session: Mapping[str, Any]) -> str:
    if session.get("freshness") in {"stale", "disconnected"}:
        return "danger"
    return "muted"


def _text(node_id: str, value: str | dict[str, str], size: str | None = None) -> dict[str, Any]:
    props: dict[str, Any] = {"text": value}
    if size is not None:
        props["size"] = size
    return {"id": node_id, "kind": "text", "props": props, "children": []}


def _button(node_id: str, label: str, action: str, *, disabled: bool = False) -> dict[str, Any]:
    return {
        "id": node_id,
        "kind": "button",
        "props": {"label": label, "action": action, "disabled": disabled},
        "children": [],
    }


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
    identities = {tuple(session["identity"]) for session in projection["sessions"]}
    if state.source not in {"all", *SOURCE_LABELS}:
        raise ValueError("unknown source filter")
    if state.selected_identity is not None and tuple(state.selected_identity) not in identities:
        state = replace(state, selected_identity=None)

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
    claude_summary = source_summaries["claude-code"]
    scene_data: dict[str, Any] = {
        "summary": {
            "codex_parallel": codex_summary["running"],
            "claude_sessions": claude_summary["sessions"],
            "claude_running": claude_summary["running"],
            "claude_waiting": claude_summary["waiting"],
            "claude_stale": claude_summary["stale"],
        },
        "claude_preview": [],
        "sessions": [],
        "detail": {},
    }

    children: list[dict[str, Any]] = [
        {
            "id": "global-overview-heading",
            "kind": "row",
            "props": {"gap": 8},
            "children": [
                _text("global-overview-title", "Agent Activity · 全局纵览", "title"),
                {"id": "global-overview-synthetic", "kind": "badge", "props": {"text": "合成"}, "children": []},
            ],
        },
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
                        _text("global-codex-label", "Codex 并行推进", "small"),
                        _text("global-codex-value", {"$path": "/summary/codex_parallel"}, "heading"),
                    ],
                },
                {
                    "id": "global-claude-metric",
                    "kind": "stack",
                    "props": {"gap": 2},
                    "children": [
                        _text("global-claude-label", "Claude Code 会话", "small"),
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
                _button("view-tab-codex", "Codex", "view.source.codex", disabled=current_source == "codex"),
                _button("view-tab-claude", "Claude Code", "view.source.claude_code", disabled=current_source == "claude-code"),
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
            "source": detail["source_type_label"],
            "session": detail["display_name"],
            "summary": _summary_preview(detail["summary"]),
            "status": detail["status_label"],
            "status_tone": _status_tone(detail),
            "freshness": detail["freshness_label"],
            "freshness_tone": _freshness_tone(detail),
            "timing": " · ".join(timing),
            "relation": "child session" if detail["has_parent"] else "top-level session",
        }
        children.extend(
            [
                _text("global-detail-session", {"$path": "/detail/session"}, "heading"),
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
        if codex_summary["stale"]:
            attention.append(f"Codex {codex_summary['stale']} 陈旧")
        if claude_summary["waiting"]:
            attention.append(f"Claude Code {claude_summary['waiting']} 等待")
        if claude_summary["stale"]:
            attention.append(f"Claude Code {claude_summary['stale']} 陈旧")
        if attention:
            children.append(_text("global-overview-attention", " · ".join(attention), "small"))
        claude_sessions = sources["claude-code"]
        children.append(_text("global-claude-preview-title", "Claude Code · 会话状态", "heading"))
        if not claude_sessions:
            children.append(_text("global-claude-preview-empty", "当前没有可显示的 Claude Code 会话。"))
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
        children.append(_text("global-source-heading", SOURCE_LABELS[current_source], "heading"))
        summary = source_summaries[current_source]
        children.append(
            _text(
                "global-source-summary",
                f"{summary['sessions']} sessions · {summary['running']} running · "
                f"{summary['waiting']} waiting · {summary['stale']} stale",
                "small",
            )
        )
        if not page_sessions:
            children.append(_text("global-source-empty", "该来源当前没有可显示的会话。"))
        for index, session in enumerate(page_sessions):
            button_id = f"global-session-detail-{state.revision}-{index}"
            detail_targets[button_id] = tuple(session["identity"])
            scene_data["sessions"].append(
                {
                    "name": session["display_name"],
                    "status": session["status_label"],
                    "freshness": session["freshness_label"],
                }
            )
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
            children.append(
                {
                    "id": f"global-session-row-{state.revision}-{index}",
                    "kind": "row",
                    "props": {"gap": 8},
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
    if action in {"view.source.codex", "view.source.claude_code"}:
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
