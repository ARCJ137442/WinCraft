"""Synthetic device-message dedupe, TTL, revocation, and read-only projection."""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, cast

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError as exc:  # pragma: no cover - exercised by the documented install path
    raise RuntimeError(
        "Install the repository validation extra: python -m pip install -r requirements-dev.txt"
    ) from exc

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "protocol" / "device-message.schema.json"
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "synthetic_messages.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
MESSAGE_VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
MAX_MESSAGES = 256
MAX_SEQUENCE_HISTORY = 4096

OriginKey = tuple[str, str, str]
MessageKey = tuple[str, str, str, str]
SequenceKey = tuple[str, str, str, int]
KIND_LABELS = {"task": "待查看", "notification": "通知摘要", "status": "来源状态"}


@dataclass(frozen=True)
class TransportReceipt:
    """Out-of-band transport evidence; never serialized into the message envelope."""

    authenticated_peer_id: str
    authenticated: bool
    origin_attested: bool
    received_at: datetime


def load_synthetic_messages() -> list[dict[str, Any]]:
    value = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("synthetic device-message fixture must contain a list")
    return value


def origin_key(message: Mapping[str, Any]) -> OriginKey:
    origin = message.get("origin")
    if not isinstance(origin, Mapping):
        raise ValueError("device message must declare an origin")
    values = (origin.get("device_id"), origin.get("source_id"), origin.get("source_instance_id"))
    if not all(isinstance(value, str) and value for value in values):
        raise ValueError("origin requires device_id, source_id, and source_instance_id")
    return cast(OriginKey, values)


def identity_key(message: Mapping[str, Any]) -> MessageKey:
    """Origin identity ignores relay hops and authenticated transport peers."""
    message_id = message.get("message_id")
    if not isinstance(message_id, str) or not message_id:
        raise ValueError("device message requires a message_id")
    return (*origin_key(message), message_id)


def _instant(value: str, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"{field} must be an RFC 3339 timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return result.astimezone(timezone.utc)


class DeviceInbox:
    """Bounded read-only inbox consumer; it does not implement or open a transport."""

    def __init__(self, *, max_messages: int = MAX_MESSAGES) -> None:
        if not 1 <= max_messages <= MAX_MESSAGES:
            raise ValueError(f"max_messages must be between 1 and {MAX_MESSAGES}")
        self.max_messages = max_messages
        self._messages: dict[MessageKey, tuple[dict[str, Any], datetime]] = {}
        self._sequences: dict[SequenceKey, MessageKey] = {}
        self._revoked: set[OriginKey] = set()

    def ingest(
        self,
        envelope: Mapping[str, Any],
        receipt: TransportReceipt,
        *,
        now: datetime | None = None,
    ) -> str:
        """Accept only an envelope paired with out-of-band authentication evidence."""
        message = copy.deepcopy(dict(envelope))
        errors = sorted(
            MESSAGE_VALIDATOR.iter_errors(message),
            key=lambda error: (list(error.absolute_path), error.message),
        )
        if errors:
            location = ".".join(str(part) for part in errors[0].absolute_path) or "<root>"
            raise ValueError(f"device message has invalid {location}: {errors[0].message}")
        if receipt.authenticated is not True:
            raise PermissionError("an authenticated external transport receipt is required")
        if receipt.received_at.tzinfo is None or receipt.received_at.utcoffset() is None:
            raise ValueError("transport receipt time must include a timezone")

        origin = origin_key(message)
        relay_trace = message.get("relay_trace", [])
        if relay_trace:
            if receipt.authenticated_peer_id != relay_trace[-1]:
                raise PermissionError("authenticated peer must match the final relay hop")
            if receipt.origin_attested is not True:
                raise PermissionError("relay authentication does not attest the claimed origin")
        elif receipt.authenticated_peer_id != origin[0]:
            raise PermissionError("direct transport peer must match the claimed origin device")

        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("now must include a timezone")
        current = current.astimezone(timezone.utc)
        received_at = receipt.received_at.astimezone(timezone.utc)
        if current < received_at:
            raise ValueError("current time cannot precede the local transport receipt")
        self._expire(current)
        if origin in self._revoked:
            return "revoked"

        issued_at = _instant(message["issued_at"], "issued_at")
        ttl = timedelta(seconds=message["ttl_seconds"])
        # Preserve the origin deadline while also bounding retention from local receipt.
        expires_at = min(issued_at + ttl, received_at + ttl)
        if current >= expires_at:
            return "expired"

        key = identity_key(message)
        if key in self._messages:
            return "duplicate"
        sequence_key: SequenceKey = (*origin, message["source_sequence"])
        existing = self._sequences.get(sequence_key)
        if existing is not None and existing != key:
            raise ValueError("source sequence was reused for a different message_id")
        if existing is None and len(self._sequences) >= MAX_SEQUENCE_HISTORY:
            raise ValueError("source sequence history limit reached; create a new source instance")
        if len(self._messages) >= self.max_messages:
            raise ValueError(f"inbox exceeds {self.max_messages} active messages")

        self._messages[key] = (message, expires_at)
        self._sequences[sequence_key] = key
        return "accepted"

    def revoke_source(self, origin: OriginKey) -> int:
        """Revoke one origin instance, remove its projection, and block replay."""
        self._revoked.add(origin)
        keys = [key for key in self._messages if key[:3] == origin]
        for key in keys:
            self._messages.pop(key)
        for sequence_key in [key for key in self._sequences if key[:3] == origin]:
            self._sequences.pop(sequence_key, None)
        return len(keys)

    def active_messages(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("now must include a timezone")
        current = current.astimezone(timezone.utc)
        self._expire(current)
        return [
            copy.deepcopy(self._messages[key][0])
            for key in sorted(
                self._messages,
                key=lambda item: (
                    item[0], item[1], item[2], self._messages[item][0]["source_sequence"], item[3]
                ),
            )
        ]

    def todo_count(self, *, now: datetime | None = None) -> int:
        return sum(
            message["message_kind"] == "task"
            for message in self.active_messages(now=now)
        )

    def _expire(self, current: datetime) -> None:
        expired = [key for key, (_message, deadline) in self._messages.items() if current >= deadline]
        for key in expired:
            self._messages.pop(key)


def synthetic_receipt(message: Mapping[str, Any], received_at: datetime) -> TransportReceipt:
    """Build a test-only receipt; this helper is not a transport authenticator."""
    relay_trace = message.get("relay_trace", [])
    if relay_trace:
        return TransportReceipt(relay_trace[-1], True, True, received_at)
    return TransportReceipt(message["origin"]["device_id"], True, False, received_at)


def build_scene(messages: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Create a read-only message summary scene; source IDs and relay traces stay local."""
    records = list(messages)
    scene_messages = [
        {
            "kind_label": KIND_LABELS[message["message_kind"]],
            "summary": message["summary"],
            "provenance_label": message["provenance"],
            "redaction_label": message["redaction"]["status"],
        }
        for message in records
    ]

    def text(node_id: str, value: str | dict[str, str], size: str | None = None) -> dict[str, Any]:
        props: dict[str, Any] = {"text": value}
        if size is not None:
            props["size"] = size
        return {"id": node_id, "kind": "text", "props": props, "children": []}

    children: list[dict[str, Any]] = [
        text("device-inbox-title", "Device Inbox · 合成只读示例", "title"),
        text("device-inbox-boundary", "仅消费外部传输认证回执；中继路径不是来源身份。"),
        {
            "id": "device-inbox-todo-count",
            "kind": "metric",
            "props": {"label": "未过期任务摘要", "value": {"$path": "/summary/todo_count"}},
            "children": [],
        },
        {"id": "device-inbox-divider", "kind": "divider", "props": {}, "children": []},
    ]
    for index, _message in enumerate(scene_messages):
        prefix = f"device-message-{index}"
        children.append(
            {
                "id": f"{prefix}-row",
                "kind": "row",
                "props": {"gap": 8},
                "children": [
                    text(f"{prefix}-kind", {"$path": f"/messages/{index}/kind_label"}),
                    text(f"{prefix}-summary", {"$path": f"/messages/{index}/summary"}),
                    {
                        "id": f"{prefix}-redaction",
                        "kind": "badge",
                        "props": {"text": {"$path": f"/messages/{index}/redaction_label"}},
                        "children": [],
                    },
                ],
            }
        )
    if not scene_messages:
        children.append(text("device-inbox-empty", "没有未过期消息。"))
    children.append(text("device-inbox-provenance", "显示摘要及来源类别；无回复、批准或写入动作。"))
    return {
        "root": {
            "id": "device-inbox-root",
            "kind": "stack",
            "props": {"gap": 8},
            "children": children,
        },
        "data": {"summary": {"todo_count": sum(item["message_kind"] == "task" for item in records)}, "messages": scene_messages},
    }
