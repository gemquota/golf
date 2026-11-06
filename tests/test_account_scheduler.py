import unittest

from account_scheduler import partition_urls_by_account


class AccountSchedulerTests(unittest.TestCase):
    def test_known_urls_are_assigned_to_their_verified_account(self):
        cohorts, unknown = partition_urls_by_account(
            ["a", "b", "c"], {"a": "U2", "b": "U1"}, 3
        )
        self.assertEqual(cohorts, {0: ["b"], 1: ["a"], 2: []})
        self.assertEqual(unknown, ["c"])

    def test_invalid_or_out_of_range_associations_are_unknown(self):
        cohorts, unknown = partition_urls_by_account(
            ["a", "b", "c", "d"], {"a": "U0", "b": "U9", "c": "bad"}, 2
        )
        self.assertEqual(cohorts, {0: [], 1: []})
        self.assertEqual(unknown, ["a", "b", "c", "d"])

    def test_empty_account_list_does_not_assign_known_urls(self):
        cohorts, unknown = partition_urls_by_account(["a"], {"a": "U1"}, 0)
        self.assertEqual(cohorts, {})
        self.assertEqual(unknown, ["a"])


if __name__ == "__main__":
    unittest.main()
