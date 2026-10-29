"""Draft read-only Harness activity aggregation over synthetic records only."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, cast

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError as exc:  # pragma: no cover - exercised by the documented install path
    raise RuntimeError(
        "Install the repository validation extra: python -m pip install -r requirements-dev.txt"
    ) from exc

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "protocol" / "activity.schema.json"
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "synthetic_activities.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
ACTIVITY_VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())

IDENTITY_FIELDS = ("device_id", "provider_id", "source_instance_id", "session_id")
NORMALIZED_STATUSES = (
    "idle",
    "running",
    "waiting_input",
    "waiting_approval",
    "blocked",
    "not_loaded",
    "completed",
    "failed",
    "cancelled",
    "unknown",
    "stale",
)
ACTIVE_STATUSES = frozenset(("running", "waiting_input", "waiting_approval"))
STATUS_LABELS = {
    "idle": "空闲",
    "running": "进行中",
    "waiting_input": "等待输入",
    "waiting_approval": "来源等待批准",
    "blocked": "来源报告阻塞",
    "not_loaded": "未加载",
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
    "unknown": "状态未知",
    "stale": "数据过期 / 来源断线",
}
FRESHNESS_LABELS = {
    "fresh": "实时",
    "stale": "过期",
    "disconnected": "断线",
    "unknown": "新鲜度未知",
}
SOURCE_TYPE_LABELS = {
    "claude-code": "Claude Code",
    "codex": "Codex",
    "codex-app": "Codex App",
    "opencode": "OpenCode",
    "deepseek-harness": "DeepSeek Harness",
    "omp": "omp",
    "fixture": "Synthetic source",
}
MAX_ACTIVITIES = 256


def load_synthetic_activities() -> list[dict[str, Any]]:
    """Load repository-owned fixture data; this function never discovers live sources."""
    value = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("synthetic activity fixture must contain a list")
    return value


def identity_key(record: Mapping[str, Any]) -> tuple[str, str, str, str]:
    """Return stable source identity; labels and model names are display-only."""
    values = tuple(record.get(field) for field in IDENTITY_FIELDS)
    if not all(isinstance(value, str) and value for value in values):
        raise ValueError("activity identity requires device/provider/instance/session IDs")
    return cast(tuple[str, str, str, str], values)


def _parse_instant(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"activity {field} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"activity {field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_and_refresh(
    records: Iterable[Mapping[str, Any]], *, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Validate a complete source snapshot and project expiry without mutating input."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must include a timezone")
    current = current.astimezone(timezone.utc)

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for index, source_record in enumerate(records):
        if not isinstance(source_record, Mapping):
            raise ValueError(f"activity record {index} must be an object")
        record = copy.deepcopy(dict(source_record))
        errors = sorted(
            ACTIVITY_VALIDATOR.iter_errors(record),
            key=lambda error: (list(error.absolute_path), error.message),
        )
        if errors:
            location = ".".join(str(part) for part in errors[0].absolute_path) or "<root>"
            raise ValueError(f"activity record {index} has invalid {location}: {errors[0].message}")

        identity = identity_key(record)
        if identity in seen:
            raise ValueError("duplicate activity identity in one source snapshot")
        seen.add(identity)

        observed_at = _parse_instant(record["observed_at"], "observed_at")
        expires_at = _parse_instant(record["expires_at"], "expires_at")
        if expires_at <= observed_at:
            raise ValueError("activity expires_at must be later than observed_at")
        if record["freshness"] == "fresh" and current >= expires_at:
            record["freshness"] = "stale"
            record["normalized_status"] = "stale"
        normalized.append(record)

    if len(normalized) > MAX_ACTIVITIES:
        raise ValueError(f"source snapshot exceeds {MAX_ACTIVITIES} activity records")

    by_identity = {identity_key(record): record for record in normalized}
    parents: dict[tuple[str, str, str, str], tuple[str, str, str, str] | None] = {}
    children: dict[tuple[str, str, str, str], set[tuple[str, str, str, str]]] = {
        identity: set() for identity in by_identity
    }
    for identity, record in by_identity.items():
        parent_id = record["parent_session_id"]
        if parent_id is None:
            parents[identity] = None
            continue
        parent = (*identity[:3], parent_id)
        if parent == identity:
            raise ValueError("activity session cannot be its own parent")
        if parent not in by_identity:
            raise ValueError("activity parent must be present in the same complete source snapshot")
        parents[identity] = parent
        children[parent].add(identity)

    for identity in parents:
        visited: set[tuple[str, str, str, str]] = set()
        current_identity: tuple[str, str, str, str] | None = identity
        while current_identity is not None:
            if current_identity in visited:
                raise ValueError("activity parent hierarchy contains a cycle")
            visited.add(current_identity)
            current_identity = parents[current_identity]

    def depth(identity: tuple[str, str, str, str]) -> int:
        result = 0
        current_identity = parents[identity]
        while current_identity is not None:
            result += 1
            current_identity = parents[current_identity]
        return result

    ordered_identities: list[tuple[str, str, str, str]] = []

    def source_order(identity: tuple[str, str, str, str]) -> tuple[int, tuple[str, str, str, str]]:
        '''按来源序号保留同层线程顺序'''
        return by_identity[identity]["source_sequence"], identity

    def visit(identity: tuple[str, str, str, str]) -> None:
        ordered_identities.append(identity)
        for child in sorted(children[identity], key=source_order):
            visit(child)

    for root in sorted(
        (identity for identity, parent in parents.items() if parent is None),
        key=source_order,
    ):
        visit(root)

    result: list[dict[str, Any]] = []
    for identity in ordered_identities:
        record = by_identity[identity]
        status = record["normalized_status"]
        freshness = record["freshness"]
        normalized_record = {
                "identity": identity,
                "source_type_label": SOURCE_TYPE_LABELS[record["source_type"]],
                "display_name": record.get("display_name") or SOURCE_TYPE_LABELS[record["source_type"]],
                "model_name": record.get("model_name") or "",
                "summary": record["summary"],
                "source_status": record["source_status"],
                "source_sequence": record["source_sequence"],
                "observed_at": record["observed_at"],
                "expires_at": record["expires_at"],
                "has_parent": record["parent_session_id"] is not None,
                "normalized_status": status,
                "status_label": STATUS_LABELS[status],
                "freshness": freshness,
                "freshness_label": FRESHNESS_LABELS[freshness],
                "depth": depth(identity),
                "is_leaf": not children[identity],
            }
        for field in ("project_label", "codex_app_thread_id", "last_output_kind"):
            if field in record:
                normalized_record[field] = record[field]
        result.append(normalized_record)
    return result


def aggregate_activities(
    records: Iterable[Mapping[str, Any]], *, now: datetime | None = None
) -> dict[str, Any]:
    """Create a deterministic projection that counts only leaf sessions."""
    sessions = validate_and_refresh(records, now=now)
    leaves = [session for session in sessions if session["is_leaf"]]
    counts = {status: 0 for status in NORMALIZED_STATUSES}
    for session in leaves:
        counts[session["normalized_status"]] += 1
    return {
        "summary": {
            "total_sessions": len(sessions),
            "counted_work_items": len(leaves),
            "active_work_items": sum(counts[status] for status in ACTIVE_STATUSES),
            "waiting_work_items": counts["waiting_input"] + counts["waiting_approval"],
            "stale_work_items": counts["stale"],
            "unknown_work_items": counts["unknown"],
            "completed_work_items": counts["completed"],
            "counting_policy": "leaf_sessions_only",
        },
        "sessions": sessions,
    }


def build_scene(projection: Mapping[str, Any]) -> dict[str, Any]:
    """Build an informational-only scene using the shared allowlisted renderer."""
    summary = projection["summary"]
    sessions = projection["sessions"]

    def text(node_id: str, value: str | dict[str, str], size: str | None = None) -> dict[str, Any]:
        props: dict[str, Any] = {"text": value}
        if size is not None:
            props["size"] = size
        return {"id": node_id, "kind": "text", "props": props, "children": []}

    def metric(node_id: str, label: str, path: str) -> dict[str, Any]:
        return {
            "id": node_id,
            "kind": "metric",
            "props": {"label": label, "value": {"$path": path}},
            "children": [],
        }

    children: list[dict[str, Any]] = [
        text("agent-board-title", "Agent Activity · 合成只读示例", "title"),
        text("agent-board-source", "数据仅来自仓库内的 synthetic fixtures；未连接真实 Harness。"),
        {
            "id": "agent-board-summary",
            "kind": "row",
            "props": {"gap": 8},
            "children": [
                metric("agent-board-active", "活动叶会话", "/summary/active_work_items"),
                metric("agent-board-waiting", "等待来源处理", "/summary/waiting_work_items"),
                metric("agent-board-stale", "过期或断线", "/summary/stale_work_items"),
            ],
        },
        {"id": "agent-board-divider", "kind": "divider", "props": {}, "children": []},
    ]
    scene_sessions: list[dict[str, str]] = []
    for index, session in enumerate(sessions):
        prefix = f"agent-session-{index}"
        indent = "　" * min(session["depth"], 8)
        scene_sessions.append(
            {
                "source": f"{indent}{session['source_type_label']} · {session['display_name']}",
                "summary": session["summary"],
                "status_label": session["status_label"],
            }
        )
        children.append(
            {
                "id": f"{prefix}-row",
                "kind": "row",
                "props": {"gap": 8},
                "children": [
                    text(f"{prefix}-source", {"$path": f"/sessions/{index}/source"}),
                    text(f"{prefix}-summary", {"$path": f"/sessions/{index}/summary"}),
                    {
                        "id": f"{prefix}-status",
                        "kind": "badge",
                        "props": {"text": {"$path": f"/sessions/{index}/status_label"}},
                        "children": [],
                    },
                ],
            }
        )
    # Only presentation values enter host-rebuildable scene data. Source IDs,
    # raw source status, model details, and control affordances remain provider-side.
    children.append(
        text("agent-board-counting-policy", "父会话作为容器呈现；统计仅计叶会话。")
    )
    return {
        "root": {
            "id": "agent-board-root",
            "kind": "stack",
            "props": {"gap": 8},
            "children": children,
        },
        "data": {
            "summary": {
                key: summary[key]
                for key in (
                    "total_sessions",
                    "counted_work_items",
                    "active_work_items",
                    "waiting_work_items",
                    "stale_work_items",
                    "unknown_work_items",
                    "completed_work_items",
                )
            },
            "sessions": scene_sessions,
        },
    }
