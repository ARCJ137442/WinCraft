import unittest
import sys
from pathlib import Path

TEST_ROOT = Path(__file__).resolve().parent
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from performance_probe import percentile, summarize


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


if __name__ == "__main__":
    unittest.main()
