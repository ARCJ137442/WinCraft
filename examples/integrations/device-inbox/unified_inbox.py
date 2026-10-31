"""Unified pending view over device messages and Agent activity.

B09-03 merges two already-normalized, read-only sources into one pending
view: device messages that arrived from outside the desktop, and Agent
activities that are waiting on a human.

Three rules define the merge:

- **De-duplication is by source identity**, never by text similarity. Two
  entries collapse only when they come from the same device, source and
  instance with the same item identity.
- **Pending kinds stay separate.** Something that needs a reply, something
  that needs a decision, and an ordinary notification are three different
  lanes; they are never merged because their titles look alike.
- **Body text grants nothing.** A notification body is display content. An
  instruction inside that body never becomes an executable action, and
  replying is a separate, explicitly authorized step.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[3]

MAX_ITEMS = 256

#: The three pending lanes. An entry belongs to exactly one.
PENDING_LANES = ("needs_reply", "needs_decision", "notification")

LANE_LABELS = {
    "needs_reply": "需要回复",
    "needs_decision": "需要决策",
    "notification": "普通通知",
}

#: How each source kind maps onto a pending lane.
#:
#: A device message declares its own lane through ``message_kind``. Agent
#: activity is mapped from its normalized status, because the Harness knows
#: whether it is waiting on input or on approval.
_MESSAGE_KIND_TO_LANE = {
    "task": "needs_reply",
    "notification": "notification",
    "status": "notification",
}
_ACTIVITY_STATUS_TO_LANE = {
    "waiting_input": "needs_reply",
    "waiting_approval": "needs_decision",
}


@dataclass(frozen=True)
class SourceIdentity:
    """Stable identity of the origin, independent of any display label."""

    device_id: str
    source_id: str
    source_instance_id: str
    item_id: str

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (
            self.device_id,
            self.source_id,
            self.source_instance_id,
            self.item_id,
        )


@dataclass(frozen=True)
class UnifiedItem:
    """One pending entry in the merged view."""

    identity: SourceIdentity
    lane: str
    origin_kind: str
    display_label: str
    summary: str
    observed_at: str
    freshness: str
    provenance: str
    #: A copyable draft, offered before any send is authorized.
    reply_draft: str | None
    #: Always empty. Body text never becomes an action.
    control_capabilities: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "identity": {
                "device_id": self.identity.device_id,
                "source_id": self.identity.source_id,
                "source_instance_id": self.identity.source_instance_id,
                "item_id": self.identity.item_id,
            },
            "lane": self.lane,
            "lane_label": LANE_LABELS[self.lane],
            "origin_kind": self.origin_kind,
            "display_label": self.display_label,
            "summary": self.summary,
            "observed_at": self.observed_at,
            "freshness": self.freshness,
            "provenance": self.provenance,
            "reply_draft": self.reply_draft,
            "control_capabilities": list(self.control_capabilities),
        }


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _instant(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def message_identity(message: Mapping[str, Any]) -> SourceIdentity:
    """Return the origin identity of a device message.

    The relay trace and any transport peer are deliberately excluded: the
    same item re-delivered through another hop is the same item.
    """
    origin = message.get("origin")
    if not isinstance(origin, Mapping):
        raise ValueError("device message must declare an origin")
    return SourceIdentity(
        device_id=_require_text(origin.get("device_id"), "origin.device_id"),
        source_id=_require_text(origin.get("source_id"), "origin.source_id"),
        source_instance_id=_require_text(
            origin.get("source_instance_id"), "origin.source_instance_id"
        ),
        item_id=_require_text(message.get("message_id"), "message_id"),
    )


def activity_identity(activity: Mapping[str, Any]) -> SourceIdentity:
    """Return the origin identity of an Agent activity record."""
    return SourceIdentity(
        device_id=_require_text(activity.get("device_id"), "device_id"),
        source_id=_require_text(activity.get("provider_id"), "provider_id"),
        source_instance_id=_require_text(
            activity.get("source_instance_id"), "source_instance_id"
        ),
        item_id=_require_text(activity.get("session_id"), "session_id"),
    )


def _message_lane(message: Mapping[str, Any]) -> str:
    kind = message.get("message_kind")
    if kind not in _MESSAGE_KIND_TO_LANE:
        raise ValueError(f"device message declares an unsupported message_kind: {kind!r}")
    return _MESSAGE_KIND_TO_LANE[kind]


def _activity_lane(activity: Mapping[str, Any]) -> str | None:
    status = activity.get("normalized_status")
    return _ACTIVITY_STATUS_TO_LANE.get(status) if isinstance(status, str) else None


def build_item_from_message(message: Mapping[str, Any]) -> UnifiedItem:
    """Project one device message into the merged view."""
    lane = _message_lane(message)
    summary = _require_text(message.get("summary"), "summary")
    issued_at = _instant(message.get("issued_at"), "issued_at")
    ttl = message.get("ttl_seconds")
    if not isinstance(ttl, int) or ttl < 1:
        raise ValueError("device message requires a positive ttl_seconds")
    freshness = "fresh" if issued_at <= datetime.now(timezone.utc) else "unknown"
    # The body may contain an instruction; it stays display-only text.
    draft = summary if lane == "needs_reply" else None
    return UnifiedItem(
        identity=message_identity(message),
        lane=lane,
        origin_kind="device_message",
        display_label=_require_text(
            message.get("origin", {}).get("source_id"), "origin.source_id"
        ),
        summary=summary,
        observed_at=issued_at.isoformat().replace("+00:00", "Z"),
        freshness=freshness,
        provenance=str(message.get("provenance", "unknown")),
        reply_draft=draft,
    )


def build_item_from_activity(activity: Mapping[str, Any]) -> UnifiedItem | None:
    """Project one Agent activity into the merged view.

    Activities that are not waiting on a human are not pending items and are
    skipped. A ``waiting_approval`` activity becomes a decision item, not an
    approval grant: the merged view never carries control capabilities.
    """
    lane = _activity_lane(activity)
    if lane is None:
        return None
    observed_at = _instant(activity.get("observed_at"), "observed_at")
    summary = str(activity.get("summary") or "").strip()
    display = str(activity.get("display_name") or "").strip()
    label = display or str(activity.get("provider_id") or "Agent")
    return UnifiedItem(
        identity=activity_identity(activity),
        lane=lane,
        origin_kind="agent_activity",
        display_label=label,
        summary=summary or label,
        observed_at=observed_at.isoformat().replace("+00:00", "Z"),
        freshness=str(activity.get("freshness") or "unknown"),
        provenance=str(activity.get("provenance") or "unknown"),
        reply_draft=None,
    )


def merge_pending(
    messages: Iterable[Mapping[str, Any]],
    activities: Iterable[Mapping[str, Any]],
) -> list[UnifiedItem]:
    """Merge both sources into one pending list, de-duplicated by identity.

    The first occurrence of an identity wins. Items are ordered by lane, then
    by observation time, then by identity, so the order is stable and does not
    depend on which source happened to deliver first.
    """
    merged: dict[tuple[str, str, str, str], UnifiedItem] = {}
    for message in messages:
        item = build_item_from_message(message)
        merged.setdefault(item.identity.as_tuple(), item)
    for activity in activities:
        item = build_item_from_activity(activity)
        if item is None:
            continue
        merged.setdefault(item.identity.as_tuple(), item)

    lane_order = {lane: index for index, lane in enumerate(PENDING_LANES)}
    ordered = sorted(
        merged.values(),
        key=lambda item: (
            lane_order[item.lane],
            item.observed_at,
            item.identity.as_tuple(),
        ),
    )
    return ordered[:MAX_ITEMS]


def build_scene(items: Iterable[UnifiedItem]) -> dict[str, Any]:
    """Build a scene that keeps the three lanes visually separate."""

    def text(node_id: str, value: str, size: str | None = None) -> dict[str, Any]:
        props: dict[str, Any] = {"text": value}
        if size:
            props["size"] = size
        return {"id": node_id, "kind": "text", "props": props, "children": []}

    children: list[dict[str, Any]] = [
        text("heading", "待办合并 · 统一视图", "title"),
        text(
            "hint",
            "正文只作展示；回复草稿可复制，发送需另行授权。",
            "body",
        ),
    ]
    for lane in PENDING_LANES:
        lane_items = [item for item in items if item.lane == lane]
        children.append(text(f"lane-{lane}", LANE_LABELS[lane], "heading"))
        if not lane_items:
            children.append(text(f"lane-{lane}-empty", "暂无", "body"))
            continue
        for item in lane_items:
            children.append(
                text(
                    f"item-{lane}-{item.identity.item_id}",
                    f"{item.display_label} · {item.summary}",
                    "body",
                )
            )
            if item.reply_draft:
                children.append(
                    text(
                        f"draft-{lane}-{item.identity.item_id}",
                        f"草稿：{item.reply_draft}",
                        "caption",
                    )
                )
    return {
        "root": {
            "id": "root",
            "kind": "stack",
            "props": {"gap": 8},
            "children": children,
        }
    }


def projection(items: Iterable[UnifiedItem]) -> dict[str, Any]:
    """Build the rebuildable projection a provider publishes."""
    collected = list(items)
    counts = {lane: 0 for lane in PENDING_LANES}
    for item in collected:
        counts[item.lane] += 1
    return {
        "counts": counts,
        "total": len(collected),
        "items": [item.to_json() for item in collected],
        "rebuildable": True,
    }
