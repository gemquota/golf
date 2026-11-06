import csv
import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import maintain_pipeline as pipeline

UTC = dt.timezone.utc


class ScrapeRunHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "base.db"
        self.history = self.root / "bonus-history.csv"
        self.started = dt.datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE sites (url TEXT PRIMARY KEY, error_code INTEGER, updated_at DATETIME)")
        conn.execute(
            "CREATE TABLE bonuses (bonus_uid TEXT, external_id TEXT, url TEXT, amount REAL, "
            "perceived_value REAL, expiry TEXT, fingerprint TEXT, mirrors TEXT, first_seen TEXT, "
            "last_seen TEXT, merchant_name TEXT, name TEXT)"
        )
        conn.execute("INSERT INTO sites VALUES (?,?,?)", (
            "https://ok.test", 200, "2026-11-01 00:05:00",
        ))
        conn.execute("INSERT INTO sites VALUES (?,?,?)", (
            "https://failed.test", 503, "2026-11-01 00:05:00",
        ))
        conn.execute("INSERT INTO bonuses VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            "new", "n1", "https://ok.test", 20, 30, None, "f1", "", "2026-11-01 00:01:00",
            "2026-11-01 00:05:00", "OK", "New bonus",
        ))
        conn.execute("INSERT INTO bonuses VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            "old", "o1", "https://ok.test", 10, 20, None, "f2", "", "2026-10-01 00:00:00",
            "2026-11-01 00:05:00", "OK", "Old bonus",
        ))
        conn.execute("INSERT INTO bonuses VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            "bad", "b1", "https://failed.test", 5, 100, None, "f3", "", "2026-11-01 00:02:00",
            "2026-11-01 00:05:00", "Failed", "Not included",
        ))
        conn.commit()
        conn.close()
        self.patcher = patch.multiple(pipeline, DB=self.db, HISTORY=self.history)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp.cleanup()

    def test_history_metrics_only_include_successful_sites(self):
        metrics = pipeline.append_history(self.started)
        self.assertEqual(metrics, {"count": 2, "new_count": 1, "sum_perceived_value": 50.0})
        with self.history.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual({row["name"] for row in rows}, {"New bonus", "Old bonus"})

    def test_run_record_is_idempotent_and_keeps_operational_metrics(self):
        finished = self.started + dt.timedelta(minutes=12)
        history = {"count": 2, "new_count": 1, "sum_perceived_value": 50.0}
        args = (self.started, finished, 4, 1, 6, 4, history)
        pipeline.record_run(*args)
        pipeline.record_run(*args)
        conn = sqlite3.connect(self.db)
        rows = conn.execute(
            "SELECT run_id, duration, count, new_count, sum_perceived_value, error_count, "
            "active_sites, moved_down, attempts, successes FROM scrape_runs"
        ).fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], pipeline.fmt(self.started))
        self.assertEqual(rows[0][1:6], (720.0, 2, 1, 50.0, 2))
        self.assertEqual(rows[0][6:], (4, 1, 6, 4))


if __name__ == "__main__":
    unittest.main()
