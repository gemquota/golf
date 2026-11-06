import csv
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from integrity_check import audit, inspect_database, inspect_history, inspect_temporary_files


class IntegrityCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / "base.db"
        self.history = self.root / "bonus_history.csv"
        self.fragments = self.root / "data"
        self.fragments.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def make_database(self, duplicate=False):
        connection = sqlite3.connect(self.database)
        connection.executescript("""
            CREATE TABLE sites (url TEXT PRIMARY KEY, error_code INTEGER, updated_at TEXT);
            CREATE TABLE bonuses (
                bonus_uid TEXT PRIMARY KEY, url TEXT, amount REAL, perceived_value REAL
            );
            CREATE TABLE scrape_runs (
                run_id TEXT, created_at TEXT, duration REAL, count INTEGER,
                new_count INTEGER, sum_perceived_value REAL, error_count INTEGER,
                active_sites INTEGER, moved_down INTEGER, attempts INTEGER, successes INTEGER
            );
        """)
        values = ("2026-11-06T00:00:00+00:00", "now", 10, 2, 1, 30, 0, 3, 0, 4, 4)
        connection.execute("INSERT INTO scrape_runs VALUES (?,?,?,?,?,?,?,?,?,?,?)", values)
        if duplicate:
            connection.execute("INSERT INTO scrape_runs VALUES (?,?,?,?,?,?,?,?,?,?,?)", values)
        connection.commit()
        connection.close()

    def write_history(self, rows):
        with self.history.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["run_ts", "uid", "url", "name"])
            writer.writeheader()
            writer.writerows(rows)

    def test_clean_database_and_history_have_no_errors(self):
        self.make_database()
        self.write_history([{
            "run_ts": "2026-11-06T00:00:00+00:00",
            "uid": "bonus-1", "url": "https://example.test", "name": "Example",
        }])
        self.assertEqual(audit(self.database, self.history, self.fragments), [])

    def test_duplicate_run_ids_are_reported_as_errors(self):
        self.make_database(duplicate=True)
        codes = {item["code"] for item in inspect_database(self.database)}
        self.assertIn("run_id_duplicate", codes)

    def test_duplicate_history_keys_are_reported(self):
        self.write_history([
            {"run_ts": "run-1", "uid": "bonus-1", "url": "https://a.test"},
            {"run_ts": "run-1", "uid": "bonus-1", "url": "https://a.test"},
        ])
        codes = {item["code"] for item in inspect_history(self.history)}
        self.assertIn("history_duplicate", codes)

    def test_stale_worker_fragments_in_scrapers_data_directory_are_warnings(self):
        fragment = self.fragments / "tmp_4.csv"
        fragment.write_text("partial", encoding="utf-8")
        old = time.time() - 25 * 60 * 60
        import os
        os.utime(fragment, (old, old))
        issues = inspect_temporary_files(self.fragments, now=time.time())
        self.assertEqual(issues[0]["code"], "stale_worker_fragment")
        self.assertEqual(issues[0]["severity"], "warning")

    def test_missing_database_is_an_error(self):
        self.assertEqual(inspect_database(self.root / "missing.db")[0]["code"], "database_missing")


if __name__ == "__main__":
    unittest.main()
