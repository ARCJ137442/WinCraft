import asyncio
import json
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace

TEST_ROOT = Path(__file__).resolve().parent
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from performance_probe import measure_refresh_soak, percentile, summarize


class FakeRefreshClient:
    def __init__(self, fail_on_mutation=False):
        self.calls = []
        self.mutations = []
        self.destroyed = False
        self.fail_on_mutation = fail_on_mutation

    async def call(self, method, params):
        self.calls.append((method, params))
        if method == "world.create":
            return {
                "world": {"id": "synthetic-world"},
                "lease": {"id": "synthetic-lease", "epoch": 1},
                "join_key": "synthetic-join-key",
            }
        if method == "world.destroy":
            self.destroyed = params["world_id"] == "synthetic-world"
            return {"destroyed": self.destroyed}
        raise AssertionError(f"unexpected RPC method: {method}")

    async def mutate(self, method, world_id, lease, **payload):
        self.mutations.append((method, world_id, lease, payload))
        if self.fail_on_mutation:
            raise RuntimeError("synthetic mutation failure")
        return {"revision": len(self.mutations) + 1}


class PerformanceProbeSummaryTests(unittest.TestCase):
    def test_percentiles_use_nearest_rank_without_interpolating_latency_samples(self):
        samples = [4.0, 1.0, 3.0, 2.0]

        self.assertEqual(percentile(samples, 0), 1.0)
        self.assertEqual(percentile(samples, 0.5), 2.0)
        self.assertEqual(percentile(samples, 0.95), 4.0)
        self.assertEqual(percentile(samples, 1), 4.0)

    def test_empty_sample_set_stays_unknown(self):
        self.assertEqual(
            summarize([]),
            {
                "count": 0,
                "min_ms": None,
                "p50_ms": None,
                "p95_ms": None,
                "p99_ms": None,
                "max_ms": None,
            },
        )

    def test_summary_contains_only_aggregate_latency_values(self):
        result = summarize([1.0, 2.0, 3.0, 4.0])

        self.assertEqual(result["count"], 4)
        self.assertEqual(result["min_ms"], 1.0)
        self.assertEqual(result["p50_ms"], 2.0)
        self.assertEqual(result["p95_ms"], 4.0)
        self.assertEqual(result["p99_ms"], 4.0)
        self.assertEqual(result["max_ms"], 4.0)
        self.assertNotIn("world_id", result)
        self.assertNotIn("lease", result)

    def test_invalid_quantile_is_rejected(self):
        for value in (-0.01, 1.01, float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                percentile([1.0], value)

    def test_visible_refresh_soak_uses_mutate_and_cleans_only_its_world(self):
        client = FakeRefreshClient()
        result = asyncio.run(
            measure_refresh_soak(
                client,
                SimpleNamespace(
                    world_cycles=1,
                    soak_visible=True,
                    soak_seconds=1,
                    payload_bytes=32,
                    refresh_interval_seconds=1,
                ),
            )
        )

        self.assertTrue(client.destroyed)
        self.assertTrue(result["cleanup_confirmed"])
        self.assertTrue(result["window_visible"])
        self.assertTrue(client.calls[0][1]["window"]["visible"])
        self.assertGreaterEqual(result["updates"], 1)
        self.assertEqual(client.mutations[0][0], "scene.replace")
        self.assertTrue(all(item[0] == "data.replace" for item in client.mutations[1:]))
        self.assertNotIn("synthetic-world", json.dumps(result))
        self.assertNotIn("synthetic-lease", json.dumps(result))

    def test_refresh_soak_cleans_its_world_when_a_mutation_fails(self):
        client = FakeRefreshClient(fail_on_mutation=True)
        with self.assertRaisesRegex(RuntimeError, "synthetic mutation failure"):
            asyncio.run(
                measure_refresh_soak(
                    client,
                    SimpleNamespace(
                        world_cycles=1,
                        soak_visible=True,
                        soak_seconds=1,
                        payload_bytes=32,
                        refresh_interval_seconds=1,
                    ),
                )
            )

        self.assertTrue(client.destroyed)


if __name__ == "__main__":
    unittest.main()
