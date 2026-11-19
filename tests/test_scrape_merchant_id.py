"""Verify successful scrapes persist the platform merchant ID."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import db
import scrape_worker


class ScrapeMerchantIdTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        self.original_cache = db._cache
        db.DB_PATH = str(Path(self.temp.name) / "scrape.sqlite")
        db._cache = {}
        db.initialize_database()
        scrape_worker.ensure_site("https://example.test")

    def tearDown(self):
        for connection in list(db._cache.values()):
            connection.close()
        db.DB_PATH = self.original_db_path
        db._cache = self.original_cache
        self.temp.cleanup()

    def test_try_scrape_persists_merchant_id_and_name(self):
        session = SimpleNamespace(cookies=SimpleNamespace(get_dict=lambda: {}))
        page = SimpleNamespace(text="<html>merchant page</html>")
        response = {"data": {"bonus": [], "promotions": []}}

        with patch.object(scrape_worker.net, "get_page_response", return_value=page), \
             patch.object(scrape_worker.net, "parse_merchant_info", return_value=("42017", "Example")), \
             patch.object(scrape_worker.net, "build_api_url", return_value="https://api.example.test"), \
             patch.object(db, "load_session", return_value=None), \
             patch.object(scrape_worker.net, "login", return_value={"token": "token", "id": "user"}), \
             patch.object(scrape_worker.net, "sync_user_data", return_value=response), \
             patch.object(scrape_worker, "record_bonus_reconciliation"):
            result = scrape_worker.try_scrape(
                session, "https://example.test", "user", "password", write_csv=False
            )

        self.assertEqual(result, (True, page.text, 0, 0))
        self.assertEqual(
            db.execute(
                "SELECT merchant_id, merchant_name FROM sites WHERE url=?",
                ("https://example.test",),
            )[0],
            ("42017", "Example"),
        )


if __name__ == "__main__":
    unittest.main()
