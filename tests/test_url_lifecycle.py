import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import maintain_pipeline as pipeline

UTC = dt.timezone.utc


class UrlLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = {
            "DB": self.root / "base.db",
            "URLS": self.root / "urls.txt",
            "DOWN": self.root / "down.txt",
            "STATE": self.root / "site_state.json",
            "ACCOUNT_SUCCESS": self.root / "account_success.json",
            "ACCOUNTS": self.root / "accounts.csv",
            "HISTORY": self.root / "history.csv",
            "RUN_LOG": self.root / "runs.csv",
        }
        self.patcher = patch.multiple(pipeline, **self.paths)
        self.patcher.start()
        conn = sqlite3.connect(self.paths["DB"])
        conn.execute("CREATE TABLE t (u TEXT PRIMARY KEY, ec INTEGER, ts DATETIME)")
        conn.execute("CREATE TABLE b (uid TEXT,eid TEXT,u TEXT,v REAL,pv REAL,raw TEXT,exp TEXT,fp TEXT,mirrors TEXT,s1 TEXT,sl TEXT,mname TEXT,name TEXT)")
        conn.commit()
        conn.close()
        self.url = "https://example.test"
        self.paths["URLS"].write_text(self.url + "\n")
        self.started = dt.datetime(2026, 1, 1, tzinfo=UTC)

    def tearDown(self):
        self.patcher.stop()
        self.temp.cleanup()

    def attempt(self, timestamp, code):
        conn = sqlite3.connect(self.paths["DB"])
        conn.execute(
            "INSERT INTO t(u,ec,ts) VALUES (?,?,?) ON CONFLICT(u) DO UPDATE SET ec=excluded.ec, ts=excluded.ts",
            (self.url, code, timestamp.strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        conn.close()

    def run_at(self, timestamp):
        return pipeline.maintain_sites(timestamp)

    def test_skipped_url_is_not_counted_as_failure(self):
        active, moved, state, attempts, successes = self.run_at(self.started)
        self.assertEqual(active, 1)
        self.assertEqual(moved, [])
        self.assertEqual(attempts, 0)
        self.assertNotIn("status", state.get(self.url, {}))
        self.assertEqual(self.paths["URLS"].read_text().strip(), self.url)

    def test_requires_failed_attempts_spanning_full_72_hours(self):
        first = self.started + dt.timedelta(minutes=5)
        self.attempt(first, 503)
        self.run_at(self.started)
        active, moved, state, attempts, successes = self.run_at(self.started + dt.timedelta(days=2))
        self.assertEqual(moved, [])
        self.assertEqual(active, 1)
        self.attempt(first + dt.timedelta(hours=72), 503)
        active, moved, state, attempts, successes = self.run_at(first + dt.timedelta(hours=72))
        self.assertEqual(moved, [self.url])
        self.assertEqual(active, 0)
        self.assertEqual(state[self.url]["status"], "down")
        self.assertEqual(self.paths["DOWN"].read_text().strip(), self.url)

    def test_success_resets_failure_window_and_recovers_quarantined_url(self):
        first = self.started + dt.timedelta(minutes=5)
        self.attempt(first, 503)
        self.run_at(self.started)
        self.attempt(first + dt.timedelta(hours=72), 503)
        active, moved, state, attempts, successes = self.run_at(first + dt.timedelta(hours=72))
        self.assertEqual(active, 0)
        self.assertEqual(moved, [self.url])
        self.assertIn(self.url, pipeline.load_lines(self.paths["DOWN"]))

        # Manually re-add a quarantined URL; a real successful attempt recovers it.
        self.paths["URLS"].write_text(self.url + "\\n")
        recovered_at = first + dt.timedelta(hours=73)
        self.attempt(recovered_at, 200)
        active, moved, state, attempts, successes = self.run_at(recovered_at)
        self.assertEqual(active, 1)
        self.assertEqual(moved, [])
        self.assertEqual(state[self.url]["status"], "up")
        self.assertIsNone(state[self.url]["first_failure_at"])
        self.assertNotIn(self.url, pipeline.load_lines(self.paths["DOWN"]))

    def test_offset_timestamps_are_normalized_to_utc(self):
        value = "2026-01-01T10:00:00+10:00"
        self.assertEqual(pipeline.sql_timestamp(value), "2026-01-01 00:00:00")


if __name__ == "__main__":
    unittest.main()
