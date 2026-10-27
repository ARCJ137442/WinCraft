import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples" / "python"))
from client import EventQueue  # noqa: E402


class EventQueueTests(unittest.TestCase):
    def state(self, sequence, event_type="window.geometry_changed", subscription="sub-a"):
        return {
            "event": "window.event",
            "data": {
                "subscription_id": subscription,
                "type": event_type,
                "delivery": "state",
                "sequence": sequence,
            },
        }

    def test_queued_state_updates_coalesce_per_subscription_and_type(self):
        queue = EventQueue(maxsize=2)
        queue.put_nowait(self.state(3))
        queue.put_nowait(self.state(7))
        queue.put_nowait(self.state(8, "window.visibility_changed"))

        self.assertEqual(queue.qsize(), 2)
        self.assertEqual(queue.get_nowait()["data"]["sequence"], 7)
        self.assertEqual(queue.get_nowait()["data"]["sequence"], 8)

    def test_occurrence_events_are_never_replaced_by_state_coalescing(self):
        queue = EventQueue(maxsize=2)
        interaction = {"event": "interaction", "data": {"id": "request-1"}}
        queue.put_nowait(interaction)
        queue.put_nowait(self.state(3))
        queue.put_nowait(self.state(7))

        self.assertEqual(queue.qsize(), 2)
        self.assertEqual(queue.get_nowait(), interaction)
        self.assertEqual(queue.get_nowait()["data"]["sequence"], 7)


if __name__ == "__main__":
    unittest.main()
