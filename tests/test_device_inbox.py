import copy
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = ROOT / "examples" / "integrations" / "device-inbox"
sys.path.insert(0, str(EXAMPLE_DIR))

from device_inbox import (  # noqa: E402
    DeviceInbox,
    TransportReceipt,
    build_scene,
    identity_key,
    load_synthetic_messages,
    origin_key,
    synthetic_receipt,
)


def walk_nodes(node):
    yield node
    for child in node.get("children", []):
        yield from walk_nodes(child)


class DeviceInboxTests(unittest.TestCase):
    def setUp(self):
        self.messages = load_synthetic_messages()
        self.now = datetime(2026, 10, 29, 10, 2, tzinfo=timezone.utc)

    def test_duplicate_message_does_not_increment_todo_count(self):
        inbox = DeviceInbox()
        message = self.messages[0]
        receipt = synthetic_receipt(message, self.now)

        self.assertEqual(inbox.ingest(message, receipt, now=self.now), "accepted")
        self.assertEqual(inbox.ingest(message, receipt, now=self.now), "duplicate")
        self.assertEqual(inbox.todo_count(now=self.now), 1)

    def test_out_of_order_messages_are_rendered_in_source_sequence_order(self):
        inbox = DeviceInbox()
        later, earlier = self.messages[0], self.messages[1]
        self.assertEqual(inbox.ingest(later, synthetic_receipt(later, self.now), now=self.now), "accepted")
        self.assertEqual(inbox.ingest(earlier, synthetic_receipt(earlier, self.now), now=self.now), "accepted")

        active = inbox.active_messages(now=self.now)
        self.assertEqual([message["source_sequence"] for message in active], [1, 2])
        self.assertEqual(inbox.todo_count(now=self.now), 2)

    def test_expired_message_is_not_retained_or_counted(self):
        inbox = DeviceInbox()
        message = self.messages[0]
        received = datetime(2026, 10, 29, 10, 4, tzinfo=timezone.utc)
        receipt = TransportReceipt("fixture-relay", True, True, received)
        after_expiry = datetime(2026, 10, 29, 10, 6, tzinfo=timezone.utc)

        self.assertEqual(inbox.ingest(message, receipt, now=after_expiry), "expired")
        self.assertEqual(inbox.active_messages(now=after_expiry), [])
        self.assertEqual(inbox.todo_count(now=after_expiry), 0)

    def test_revocation_removes_existing_message_and_blocks_replay(self):
        inbox = DeviceInbox()
        message = self.messages[0]
        receipt = synthetic_receipt(message, self.now)
        self.assertEqual(inbox.ingest(message, receipt, now=self.now), "accepted")

        self.assertEqual(inbox.revoke_source(origin_key(message)), 1)
        self.assertEqual(inbox.todo_count(now=self.now), 0)
        self.assertEqual(inbox.ingest(message, receipt, now=self.now), "revoked")

    def test_relay_trace_is_not_source_identity_or_authentication(self):
        inbox = DeviceInbox()
        relayed = copy.deepcopy(self.messages[0])
        source_identity = identity_key(relayed)
        unverified = TransportReceipt("fixture-relay", True, False, self.now)
        with self.assertRaisesRegex(PermissionError, "does not attest"):
            inbox.ingest(relayed, unverified, now=self.now)

        self.assertEqual(inbox.ingest(relayed, synthetic_receipt(relayed, self.now), now=self.now), "accepted")
        changed_trace = copy.deepcopy(relayed)
        changed_trace["relay_trace"] = ["another-relay"]
        self.assertEqual(identity_key(changed_trace), source_identity)
        alternate_receipt = TransportReceipt("another-relay", True, True, self.now)
        self.assertEqual(inbox.ingest(changed_trace, alternate_receipt, now=self.now), "duplicate")

    def test_unauthenticated_or_wrong_direct_peer_is_rejected(self):
        inbox = DeviceInbox()
        message = copy.deepcopy(self.messages[1])
        with self.assertRaisesRegex(PermissionError, "authenticated external transport"):
            inbox.ingest(message, TransportReceipt("fixture-phone", False, False, self.now), now=self.now)
        with self.assertRaisesRegex(PermissionError, "direct transport peer"):
            inbox.ingest(message, TransportReceipt("other-device", True, False, self.now), now=self.now)

    def test_source_sequence_cannot_be_reused_for_another_message(self):
        inbox = DeviceInbox()
        message = self.messages[0]
        inbox.ingest(message, synthetic_receipt(message, self.now), now=self.now)
        conflict = copy.deepcopy(message)
        conflict["message_id"] = "different-id-same-sequence"
        with self.assertRaisesRegex(ValueError, "sequence was reused"):
            inbox.ingest(conflict, synthetic_receipt(conflict, self.now), now=self.now)

    def test_scene_contains_only_redacted_read_only_projection(self):
        inbox = DeviceInbox()
        for message in self.messages:
            inbox.ingest(message, synthetic_receipt(message, self.now), now=self.now)
        scene = build_scene(inbox.active_messages(now=self.now))
        schema = json.loads((ROOT / "protocol" / "scene.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(scene)
        nodes = list(walk_nodes(scene["root"]))
        self.assertFalse(any(node["kind"] in {"button", "input", "textarea"} for node in nodes))
        for node in nodes:
            self.assertFalse({"action", "context_action", "native_window_action"} & set(node.get("props", {})))
        rendered = json.dumps(scene["data"], ensure_ascii=False)
        self.assertNotIn("fixture-phone", rendered)
        self.assertNotIn("fixture-task-1", rendered)
        self.assertNotIn("fixture-relay", rendered)

    def test_envelope_schema_rejects_raw_body_and_missing_origin(self):
        schema = json.loads((ROOT / "protocol" / "device-message.schema.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for invalid_name in ("invalid_raw_body.json", "invalid_missing_origin.json"):
            invalid = json.loads((EXAMPLE_DIR / "fixtures" / invalid_name).read_text(encoding="utf-8"))
            self.assertFalse(validator.is_valid(invalid), invalid_name)


if __name__ == "__main__":
    unittest.main()
