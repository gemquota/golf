"""Regression tests for current-run scheduling semantics."""
import unittest
from unittest.mock import patch

from account_scheduler import partition_urls_by_account


class ScrapeRunSemanticsTests(unittest.TestCase):
    def test_persisted_success_is_not_a_scheduler_exclusion(self):
        # The scheduler partitions configured URLs independently of historical
        # SQLite success. Resume filtering is a separate CLI/run-level decision.
        cohorts, unknown = partition_urls_by_account(
            ["previously-successful", "new"], {}, 1
        )
        self.assertEqual(cohorts, {0: []})
        self.assertEqual(unknown, ["previously-successful", "new"])

    def test_verified_account_cohort_survives_unrelated_unknown_urls(self):
        cohorts, unknown = partition_urls_by_account(
            ["known", "unknown"], {"known": "U2"}, 2
        )
        self.assertEqual(cohorts[1], ["known"])
        self.assertEqual(unknown, ["unknown"])


if __name__ == "__main__":
    unittest.main()
