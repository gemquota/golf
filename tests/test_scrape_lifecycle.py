import unittest
from unittest.mock import Mock, patch

import scraper
import server


class ScrapeLifecycleTests(unittest.TestCase):
    def test_worker_session_is_closed_when_worker_fails(self):
        session = Mock()
        with patch.object(scraper.net, "create_session", return_value=session):
            with patch.object(scraper, "_worker_tasks", side_effect=RuntimeError("worker failed")):
                with self.assertRaisesRegex(RuntimeError, "worker failed"):
                    scraper.worker(0, {}, {}, 0, 0, False, 1, [], [], None)
        session.close.assert_called_once()

    def test_run_state_is_reset_when_scrape_raises(self):
        server.IS_RUNNING = True
        with patch.object(scraper, "_run_scrape", side_effect=RuntimeError("scrape failed")):
            with self.assertRaisesRegex(RuntimeError, "scrape failed"):
                scraper.run_scrape()
        self.assertFalse(server.IS_RUNNING)

    def test_run_state_is_reset_after_success(self):
        expected = object()
        with patch.object(scraper, "_run_scrape", return_value=expected):
            self.assertIs(scraper.run_scrape(), expected)
        self.assertFalse(server.IS_RUNNING)


if __name__ == "__main__":
    unittest.main()
