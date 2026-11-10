import unittest

import config


class TemporaryThrottleModeTests(unittest.TestCase):
    def test_temporary_mode_enforces_one_worker(self):
        self.assertTrue(config.TEMPORARY_SINGLE_WORKER_MODE)
        self.assertEqual(config.SCRAPE_WORKERS, 1)

    def test_temporary_mode_uses_five_to_ten_second_delay(self):
        self.assertEqual(config.MIN_DELAY, 5.0)
        self.assertEqual(config.MAX_DELAY, 10.0)


if __name__ == "__main__":
    unittest.main()
