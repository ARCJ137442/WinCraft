'''Unit tests for the private crash-probe handoff record.
- 🎯Keep temporary recovery inputs explicit and typed.
- 🤖Agent-generated tests, not yet human-reviewed【2026-10-31】
'''

import sys
import unittest
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parent
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from crash_recovery_probe import is_host_disconnect_event, parse_crash_owner_record


class CrashOwnerRecordTests(unittest.TestCase):
    def test_valid_private_record_keeps_only_recovery_fields(self):
        record = parse_crash_owner_record(
            '{"world_id":"synthetic-world",'
            '"join_key":"synthetic-join-key","owner_epoch":2,"ignored":"value"}'
        )

        self.assertEqual(
            record,
            {
                'world_id': 'synthetic-world',
                'join_key': 'synthetic-join-key',
                'owner_epoch': 2,
            },
        )

    def test_invalid_join_fields_and_boolean_epoch_are_rejected(self):
        for content in (
            '{"world_id":"synthetic-world","owner_epoch":2}',
            '{"world_id":"synthetic-world","join_key":"key","owner_epoch":true}',
            '[]',
        ):
            with self.subTest(content=content), self.assertRaises(ValueError):
                parse_crash_owner_record(content)


class HostDisconnectEventTests(unittest.TestCase):
    def test_only_terminal_connection_events_confirm_host_loss(self):
        for event_name in ('connection.error', 'connection.closed'):
            with self.subTest(event=event_name):
                self.assertTrue(is_host_disconnect_event({'event': event_name}))

        for event_name in ('world.snapshot', 'interaction', 'provider.error'):
            with self.subTest(event=event_name):
                self.assertFalse(is_host_disconnect_event({'event': event_name}))


if __name__ == '__main__':
    unittest.main()
