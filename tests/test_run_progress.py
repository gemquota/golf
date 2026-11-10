import unittest

from run_progress import RunProgress


class RunProgressTests(unittest.TestCase):
    def test_progress_is_cumulative_across_account_batches(self):
        progress = RunProgress(3)
        first = progress.apply({"site_url": "https://a.test", "N": 1, "index": 1})
        second = progress.apply({"site_url": "https://b.test", "N": 2, "index": 2})
        third = progress.apply({"site_url": "https://c.test", "N": 1, "index": 1})

        self.assertEqual(
            [(event["index"], event["N"]) for event in (first, second, third)],
            [(1, 3), (2, 3), (3, 3)],
        )

    def test_fallback_attempt_does_not_count_url_twice(self):
        progress = RunProgress(2)
        progress.apply({"site_url": "https://a.test"})
        fallback = progress.apply({"site_url": "https://a.test", "N": 1})

        self.assertEqual(fallback["index"], 1)
        self.assertEqual(fallback["N"], 2)

    def test_event_is_not_mutated(self):
        progress = RunProgress(1)
        original = {"site_url": "https://a.test", "index": 9, "N": 9}
        progress.apply(original)
        self.assertEqual(original, {"site_url": "https://a.test", "index": 9, "N": 9})


if __name__ == "__main__":
    unittest.main()
