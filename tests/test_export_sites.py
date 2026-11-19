"""CSV export tests for merchant-ID grouped site records."""
import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from export_sites import export_sites


class SiteExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "sites.sqlite"
        self.output = self.root / "sites_by_merchant.csv"
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE sites (
                url TEXT PRIMARY KEY,
                merchant_id TEXT,
                merchant_name TEXT,
                active INTEGER,
                updated_at TEXT,
                error_code INTEGER
            )
        """)
        conn.executemany(
            "INSERT INTO sites(url, merchant_id, merchant_name, active, updated_at, error_code) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("https://ten.example", "10", "Ten", 1, "2026-01-02", None),
                ("https://two-b.example", "2", "Two", 1, "2026-01-03", None),
                ("https://two-a.example", "2", "Two", 0, "2026-01-01", 403),
                ("https://unknown-a.example", None, "Unknown", 1, None, None),
                ("https://unknown-b.example", None, "Unknown", 1, None, None),
            ],
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_groups_mirrors_and_sorts_numeric_ids(self):
        count = export_sites(self.db_path, self.output)
        self.assertEqual(count, 4)

        with self.output.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual([row["merchant_id"] for row in rows], ["2", "10", "", ""])
        self.assertEqual(rows[0]["merchant_name"], "Two")
        self.assertEqual(
            rows[0]["urls"],
            "https://two-a.example | https://two-b.example",
        )
        self.assertEqual(rows[0]["url_count"], "2")
        self.assertEqual(rows[0]["active_values"], "0 | 1")
        self.assertEqual(rows[0]["error_codes"], "403")
        self.assertEqual(rows[2]["urls"], "https://unknown-a.example")
        self.assertEqual(rows[3]["urls"], "https://unknown-b.example")

    def test_missing_merchant_id_column_fails_clearly(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("ALTER TABLE sites DROP COLUMN merchant_id")
        conn.commit()
        conn.close()

        with self.assertRaisesRegex(RuntimeError, "merchant_id column is missing"):
            export_sites(self.db_path, self.output)


if __name__ == "__main__":
    unittest.main()
