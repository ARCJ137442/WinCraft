from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / 'examples' / 'integrations' / 'agent-board' / 'decisions'
sys.path.insert(0, str(DECISIONS))

from decision_cards import (  # noqa: E402
    CardState,
    DecisionError,
    DecisionOutcome,
    DecisionRegistry,
    DecisionRequest,
    build_scene,
    render_without_secrets,
)

BASE = datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc)


def request(**overrides):
    fields = {
        'source_id': 'codex-cli',
        'source_type': 'codex',
        'session_id': 'session-1',
        'request_id': 'req-1',
        'operation': 'apply_patch',
        'operation_summary': 'Apply the pending patch to crates/wincraft-core',
        'issued_at': BASE,
        'expires_at': BASE + timedelta(minutes=10),
        'details': {'files': 1},
    }
    fields.update(overrides)
    return DecisionRequest(**fields)


class DecisionCardTests(unittest.TestCase):
    def setUp(self):
        self.registry = DecisionRegistry()

    def test_showing_a_task_does_not_grant_approval_right(self):
        card = self.registry.open(request())
        rendered = card.to_json()
        self.assertEqual(rendered['control_capabilities'], [])
        self.assertEqual(rendered['state'], 'pending')
        # A pending card carries no outcome: it cannot report an approval.
        self.assertIsNone(rendered['outcome'])

    def test_card_names_the_exact_operation_and_its_origin(self):
        card = self.registry.open(request())
        rendered = card.to_json()
        self.assertEqual(rendered['operation'], 'apply_patch')
        self.assertEqual(rendered['operation_summary'],
                         'Apply the pending patch to crates/wincraft-core')
        self.assertEqual(rendered['source_id'], 'codex-cli')
        self.assertEqual(rendered['session_id'], 'session-1')
        self.assertEqual(len(rendered['operation_digest']), 64)

    def test_card_never_carries_a_token(self):
        card = self.registry.open(request(details={'token': 'secret-token-value'}))
        safe = render_without_secrets(card.to_json())
        self.assertNotIn('token', safe)
        self.assertNotIn('secret-token-value', str(safe))
        self.assertNotIn('details', safe)

    def test_the_same_request_cannot_be_opened_twice(self):
        self.registry.open(request())
        with self.assertRaisesRegex(DecisionError, 'DUPLICATE_REQUEST'):
            self.registry.open(request())

    def test_a_decision_cannot_be_given_twice(self):
        card = self.registry.open(request())
        self.registry.decide(card.card_id, DecisionOutcome.APPROVED, now=BASE)
        with self.assertRaisesRegex(DecisionError, 'ALREADY_RESOLVED'):
            self.registry.decide(card.card_id, DecisionOutcome.APPROVED, now=BASE)

    def test_a_revoked_card_cannot_be_approved(self):
        card = self.registry.open(request())
        self.registry.revoke(card.card_id, now=BASE)
        with self.assertRaisesRegex(DecisionError, 'REVOKED'):
            self.registry.decide(card.card_id, DecisionOutcome.APPROVED, now=BASE)

    def test_an_expired_card_cannot_be_approved(self):
        card = self.registry.open(request())
        later = BASE + timedelta(minutes=11)
        with self.assertRaisesRegex(DecisionError, 'EXPIRED'):
            self.registry.decide(card.card_id, DecisionOutcome.APPROVED, now=later)
        self.assertEqual(self.registry.get(card.card_id).state, CardState.EXPIRED)

    def test_expired_cards_drop_out_of_the_pending_list(self):
        self.registry.open(request(request_id='req-1'))
        self.registry.open(request(request_id='req-2'))
        later = BASE + timedelta(minutes=11)
        self.assertEqual(self.registry.pending(now=later), [])

    def test_denial_is_recorded_like_approval(self):
        card = self.registry.open(request())
        decided = self.registry.decide(card.card_id, DecisionOutcome.DENIED, now=BASE)
        self.assertEqual(decided.state, CardState.ANSWERED)
        self.assertEqual(decided.outcome, DecisionOutcome.DENIED)

    def test_a_timeout_records_an_unknown_outcome_and_never_replays(self):
        card = self.registry.open(request())
        self.registry.decide(card.card_id, DecisionOutcome.APPROVED, now=BASE)
        failed = self.registry.record_delivery_failure(
            card.card_id, 'authority did not acknowledge within the timeout',
            now=BASE,
        )
        self.assertEqual(failed.state, CardState.DELIVERY_UNKNOWN)
        self.assertIsNotNone(failed.delivery_note)
        # The answer is still recorded; the registry does not retry the effect.
        self.assertEqual(failed.outcome, DecisionOutcome.APPROVED)
        with self.assertRaisesRegex(DecisionError, 'ALREADY_RESOLVED'):
            self.registry.decide(card.card_id, DecisionOutcome.APPROVED, now=BASE)

    def test_delivery_failure_requires_an_answered_card(self):
        card = self.registry.open(request())
        with self.assertRaisesRegex(DecisionError, 'NOT_ANSWERED'):
            self.registry.record_delivery_failure(card.card_id, 'timeout', now=BASE)

    def test_the_digest_changes_when_the_operation_changes(self):
        first = request().digest()
        second = request(operation_summary='Apply a different patch').digest()
        self.assertNotEqual(first, second)

    def test_scene_shows_the_operation_without_a_token(self):
        card = self.registry.open(request(details={'token': 'secret-token-value'}))
        scene = build_scene(self.registry.render(now=BASE))
        rendered = str(scene)
        self.assertIn('apply_patch', rendered)
        self.assertNotIn('secret-token-value', rendered)

    def test_invalid_request_is_refused(self):
        with self.assertRaisesRegex(DecisionError, 'INVALID_REQUEST'):
            self.registry.open(request(operation_summary=''))
        with self.assertRaisesRegex(DecisionError, 'INVALID_REQUEST'):
            self.registry.open(request(
                issued_at=BASE,
                expires_at=BASE,
            ))


if __name__ == '__main__':
    unittest.main()
