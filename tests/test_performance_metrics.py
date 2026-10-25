#!/usr/bin/env python3
"""Unit tests for the response-time and throughput-fairness metrics."""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from performance_metrics import average_ping_ms, jain_fairness_index


class PerformanceMetricsTest(unittest.TestCase):
    def test_parse_iputils_rtt_summary(self):
        output = "10 packets transmitted, 10 received\nrtt min/avg/max/mdev = 1.0/2.5/4.0/0.3 ms\n"
        self.assertEqual(average_ping_ms(output, "baseline"), 2.5)

    def test_parse_round_trip_summary_variant(self):
        output = "round-trip min/avg/max/stddev = 1.0/3.25/5.0/0.4 ms\n"
        self.assertEqual(average_ping_ms(output, "loaded"), 3.25)

    def test_reject_missing_rtt_summary(self):
        with self.assertRaisesRegex(RuntimeError, "Could not parse"):
            average_ping_ms("ping failed", "baseline")

    def test_jain_index_for_equal_and_unequal_rates(self):
        self.assertAlmostEqual(jain_fairness_index([5.0, 5.0]), 1.0)
        self.assertAlmostEqual(jain_fairness_index([10.0, 0.0]), 0.5)

    def test_jain_index_rejects_invalid_rates(self):
        for rates in ([], [0.0, 0.0], [-1.0, 2.0]):
            with self.subTest(rates=rates):
                with self.assertRaises(ValueError):
                    jain_fairness_index(rates)


if __name__ == "__main__":
    unittest.main(verbosity=2)
