"""Decision cards: a bounded, non-replayable approval handshake.

B08-04 turns "this session is waiting on you" into an explicit decision the
user can act on once, and that goes back to the authority that raised it.

The rules this module enforces:

- **Displaying is not approving.** A card renders a pending decision; it never
  carries an approval right of its own.
- **A card names the exact operation and its origin.** The card carries a
  digest of the operation, the source and session that asked, and an expiry.
  It never carries a token, a secret, or a raw command.
- **One decision, one effect.** A card that was revoked, that expired, or that
  was already answered elsewhere cannot be approved a second time.
- **A timeout reads back; it does not replay.** When the answer cannot be
  delivered, the outcome is recorded as "unknown" and read back to the user.
  The side effect is never blindly repeated.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Iterable, Mapping

MAX_OPERATION_SUMMARY_CHARS = 512
MAX_CARDS = 256


class CardState(str, Enum):
    """Lifecycle of one decision card."""

    PENDING = 'pending'
    ANSWERED = 'answered'
    REVOKED = 'revoked'
    EXPIRED = 'expired'
    DELIVERY_UNKNOWN = 'delivery_unknown'


class DecisionOutcome(str, Enum):
    """What the user chose."""

    APPROVED = 'approved'
    DENIED = 'denied'


class DecisionError(RuntimeError):
    """A refusal that carries a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f'{code}: {message}')


@dataclass(frozen=True)
class DecisionRequest:
    """A pending decision raised by one authoritative source."""

    source_id: str
    source_type: str
    session_id: str
    request_id: str
    operation: str
    operation_summary: str
    issued_at: datetime
    expires_at: datetime
    #: Extra detail the card may show. It must not contain secrets.
    details: Mapping[str, Any] = field(default_factory=dict)

    def digest(self) -> str:
        """Return a stable digest of the operation this card asks about.

        The digest binds the answer to one exact operation. It is computed
        over the declared fields only, never over a token.
        """
        payload = json.dumps(
            {
                'source_id': self.source_id,
                'source_type': self.source_type,
                'session_id': self.session_id,
                'request_id': self.request_id,
                'operation': self.operation,
                'operation_summary': self.operation_summary,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        )
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()


@dataclass
class DecisionCard:
    """A card plus its mutable lifecycle state."""

    request: DecisionRequest
    state: CardState = CardState.PENDING
    outcome: DecisionOutcome | None = None
    decided_at: datetime | None = None
    #: Set when the decision could not be delivered to the authority.
    delivery_note: str | None = None

    @property
    def card_id(self) -> str:
        return f'{self.request.source_id}:{self.request.request_id}'

    @property
    def digest(self) -> str:
        return self.request.digest()

    def to_json(self) -> dict[str, Any]:
        """Render the card.

        The rendered card never carries a token: only the declared operation,
        its digest, the origin, the timing and the current state.
        """
        return {
            'card_id': self.card_id,
            'source_id': self.request.source_id,
            'source_type': self.request.source_type,
            'session_id': self.request.session_id,
            'request_id': self.request.request_id,
            'operation': self.request.operation,
            'operation_summary': self.request.operation_summary,
            'operation_digest': self.digest,
            'issued_at': self.request.issued_at.isoformat().replace('+00:00', 'Z'),
            'expires_at': self.request.expires_at.isoformat().replace('+00:00', 'Z'),
            'state': self.state.value,
            'outcome': self.outcome.value if self.outcome else None,
            'decided_at': (
                self.decided_at.isoformat().replace('+00:00', 'Z')
                if self.decided_at
                else None
            ),
            'details': dict(self.request.details),
            'delivery_note': self.delivery_note,
            'control_capabilities': [],
        }


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError('now must include a timezone')
    return current.astimezone(timezone.utc)


def _validate(request: DecisionRequest) -> None:
    for name in ('source_id', 'source_type', 'session_id', 'request_id', 'operation'):
        value = getattr(request, name)
        if not isinstance(value, str) or not value:
            raise DecisionError('INVALID_REQUEST', f'{name} must be a non-empty string')
    if not isinstance(request.operation_summary, str) or not request.operation_summary:
        raise DecisionError('INVALID_REQUEST', 'operation_summary must be a non-empty string')
    if len(request.operation_summary) > MAX_OPERATION_SUMMARY_CHARS:
        raise DecisionError(
            'INVALID_REQUEST',
            f'operation_summary exceeds {MAX_OPERATION_SUMMARY_CHARS} characters',
        )
    for name in ('issued_at', 'expires_at'):
        value = getattr(request, name)
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f'{name} must include a timezone')
    if request.expires_at <= request.issued_at:
        raise DecisionError('INVALID_REQUEST', 'expires_at must be after issued_at')
    if request.details and not isinstance(request.details, Mapping):
        raise DecisionError('INVALID_REQUEST', 'details must be an object')


class DecisionRegistry:
    """Holds pending decision cards for one source family."""

    def __init__(self, *, max_cards: int = MAX_CARDS) -> None:
        self._cards: dict[str, DecisionCard] = {}
        self._max_cards = max_cards

    def open(self, request: DecisionRequest) -> DecisionCard:
        """Register a pending decision and return its card."""
        _validate(request)
        card = DecisionCard(request=request)
        if card.card_id in self._cards:
            raise DecisionError(
                'DUPLICATE_REQUEST',
                'this request id is already open for this source',
            )
        if len(self._cards) >= self._max_cards:
            raise DecisionError('LIMIT', 'too many open decision cards')
        self._cards[card.card_id] = card
        return card

    def get(self, card_id: str) -> DecisionCard:
        card = self._cards.get(card_id)
        if card is None:
            raise DecisionError('NOT_FOUND', 'decision card not found')
        return card

    def pending(self, *, now: datetime | None = None) -> list[DecisionCard]:
        """List cards that are still open, expiring stale ones first."""
        current = _now(now)
        for card in self._cards.values():
            if (
                card.state is CardState.PENDING
                and card.request.expires_at <= current
            ):
                card.state = CardState.EXPIRED
        return [
            card for card in self._cards.values() if card.state is CardState.PENDING
        ]

    def revoke(self, card_id: str, *, now: datetime | None = None) -> DecisionCard:
        """Revoke a card, for example because the source withdrew the ask."""
        current = _now(now)
        card = self.get(card_id)
        if card.state is not CardState.PENDING:
            raise DecisionError('ALREADY_RESOLVED', f'card is {card.state.value}')
        if card.request.expires_at <= current:
            card.state = CardState.EXPIRED
            raise DecisionError('EXPIRED', 'the decision request expired')
        card.state = CardState.REVOKED
        return card

    def decide(
        self,
        card_id: str,
        outcome: DecisionOutcome,
        *,
        now: datetime | None = None,
    ) -> DecisionCard:
        """Record the user's answer on a card.

        A revoked, expired or already-answered card refuses a second answer.
        This is the guard that prevents one request from being approved twice.
        """
        current = _now(now)
        card = self.get(card_id)
        if card.state is CardState.REVOKED:
            raise DecisionError('REVOKED', 'the decision request was revoked')
        if card.state is CardState.EXPIRED:
            raise DecisionError('EXPIRED', 'the decision request expired')
        if card.state is not CardState.PENDING:
            raise DecisionError(
                'ALREADY_RESOLVED',
                f'card was already {card.state.value}',
            )
        if card.request.expires_at <= current:
            card.state = CardState.EXPIRED
            raise DecisionError('EXPIRED', 'the decision request expired')
        card.state = CardState.ANSWERED
        card.outcome = outcome
        card.decided_at = current
        return card

    def record_delivery_failure(
        self,
        card_id: str,
        note: str,
        *,
        now: datetime | None = None,
    ) -> DecisionCard:
        """Record that the answer could not be delivered to the authority.

        The card becomes ``delivery_unknown`` rather than being retried. The
        side effect may or may not have happened; only the authority can
        resolve that, so the user is told the outcome is unknown.
        """
        card = self.get(card_id)
        if card.state is not CardState.ANSWERED:
            raise DecisionError(
                'NOT_ANSWERED', 'only an answered card can record a delivery failure'
            )
        card.state = CardState.DELIVERY_UNKNOWN
        card.delivery_note = note[:MAX_OPERATION_SUMMARY_CHARS]
        return card

    def render(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        """Render every card, newest first."""
        current = _now(now)
        self.pending(now=current)
        cards = sorted(
            self._cards.values(),
            key=lambda card: card.request.issued_at,
            reverse=True,
        )
        return [card.to_json() for card in cards]


def build_scene(cards: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Build a scene that shows each decision with its exact operation."""

    def text(node_id: str, value: str, size: str | None = None) -> dict[str, Any]:
        props: dict[str, Any] = {'text': value}
        if size:
            props['size'] = size
        return {'id': node_id, 'kind': 'text', 'props': props, 'children': []}

    children: list[dict[str, Any]] = [
        text('heading', '决策卡 · 待确认操作', 'title'),
        text(
            'hint',
            '显示不等于授权；每张卡只对应一次操作，确认后不可重复批准。',
            'body',
        ),
    ]
    for card in cards:
        card_id = str(card.get('card_id', 'unknown'))
        children.append(text(f'card-{card_id}-source', f"来源：{card.get('source_id')}", 'heading'))
        children.append(
            text(
                f'card-{card_id}-operation',
                f"操作：{card.get('operation')} · {card.get('operation_summary')}",
                'body',
            )
        )
        children.append(
            text(
                f'card-{card_id}-digest',
                f"摘要指纹：{str(card.get('operation_digest'))[:16]}",
                'caption',
            )
        )
        children.append(
            text(f'card-{card_id}-state', f"状态：{card.get('state')}", 'caption')
        )
    return {
        'root': {
            'id': 'root',
            'kind': 'stack',
            'props': {'gap': 8},
            'children': children,
        }
    }


def render_without_secrets(card: Mapping[str, Any]) -> dict[str, Any]:
    """Return the card fields that are safe to show or log.

    Any field that could carry a credential is dropped rather than masked,
    so a token cannot reach a scene, a log line or a screenshot.
    """
    allowed = (
        'card_id',
        'source_id',
        'source_type',
        'session_id',
        'request_id',
        'operation',
        'operation_summary',
        'operation_digest',
        'issued_at',
        'expires_at',
        'state',
        'outcome',
        'decided_at',
    )
    return {key: copy.deepcopy(card[key]) for key in allowed if key in card}
