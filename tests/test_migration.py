"""Migration: old golfed schema → canonical names with data intact."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import db


LEGACY_DDL = """
CREATE TABLE t (
    u TEXT PRIMARY KEY,
    m TEXT,
    p TEXT,
    g TEXT,
    a INTEGER DEFAULT 1,
    ts DATETIME,
    ec INTEGER
);
CREATE TABLE b (
    uid TEXT PRIMARY KEY,
    eid TEXT,
    u TEXT,
    v REAL,
    pv REAL,
    w REAL,
    c TEXT,
    t TEXT,
    raw TEXT,
    h TEXT,
    exp TEXT,
    fp TEXT,
    mirrors TEXT,
    s1 TEXT,
    sl TEXT,
    mname TEXT,
    name TEXT
);
CREATE TABLE s (
    uid TEXT,
    u TEXT,
    ck BLOB,
    data BLOB,
    ua TEXT,
    ts DATETIME,
    PRIMARY KEY (uid, u)
);
CREATE TABLE m (
    rid INTEGER PRIMARY KEY,
    ts DATETIME,
    dur REAL,
    cnt INTEGER,
    new INTEGER,
    spv REAL,
    err INTEGER
);
CREATE TABLE l (
    ts DATETIME DEFAULT CURRENT_TIMESTAMP,
    lvl TEXT,
    src TEXT,
    msg TEXT
);
"""


class UngolfMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "legacy.sqlite"
        self.original_db_path = db.DB_PATH
        self.original_cache = db._cache
        db.DB_PATH = str(self.db_path)
        db._cache = {}

        conn = sqlite3.connect(self.db_path)
        conn.executescript(LEGACY_DDL)
        conn.execute(
            "INSERT INTO t(u, m, p, g, a, ts, ec) VALUES (?,?,?,?,?,?,?)",
            (
                "https://example.test/a",
                "Example Casino",
                "https://ref.example/a",
                "ex",
                1,
                "2026-01-01 00:00:00",
                200,
            ),
        )
        conn.execute(
            "INSERT INTO b(uid,eid,u,v,pv,raw,exp,fp,mirrors,s1,sl,mname,name) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "uid-1",
                "eid-1",
                "https://example.test/a",
                50.0,
                42.5,
                '{"amount":50}',
                "2026-12-01",
                "fp-1",
                "[]",
                "2026-01-01",
                "2026-01-02",
                "Example Casino",
                "Welcome",
            ),
        )
        conn.execute(
            "INSERT INTO l(lvl, src, msg) VALUES (?,?,?)",
            ("INFO", "test", "hello"),
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        for connection in list(db._cache.values()):
            connection.close()
        db.DB_PATH = self.original_db_path
        db._cache = self.original_cache
        self.temp.cleanup()

    def test_migrate_renames_and_preserves_rows(self):
        db.migrate_ungolf_schema()

        conn = sqlite3.connect(self.db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        self.assertIn("sites", tables)
        self.assertIn("bonuses", tables)
        self.assertIn("sessions", tables)
        self.assertIn("scrape_runs", tables)
        self.assertIn("logs", tables)
        self.assertNotIn("t", tables)
        self.assertNotIn("b", tables)

        site_cols = {r[1] for r in conn.execute("PRAGMA table_info(sites)")}
        self.assertTrue({"url", "merchant_name", "error_code", "updated_at"} <= site_cols)
        self.assertNotIn("u", site_cols)
        self.assertNotIn("ec", site_cols)

        row = conn.execute(
            "SELECT url, merchant_name, error_code FROM sites"
        ).fetchone()
        self.assertEqual(row, ("https://example.test/a", "Example Casino", 200))

        bonus = conn.execute(
            "SELECT bonus_uid, external_id, url, amount, perceived_value, merchant_name, name "
            "FROM bonuses"
        ).fetchone()
        self.assertEqual(
            bonus,
            ("uid-1", "eid-1", "https://example.test/a", 50.0, 42.5, "Example Casino", "Welcome"),
        )

        log_row = conn.execute(
            "SELECT level, source, message FROM logs"
        ).fetchone()
        self.assertEqual(log_row, ("INFO", "test", "hello"))
        conn.close()

    def test_migration_is_idempotent(self):
        db.migrate_ungolf_schema()
        db.migrate_ungolf_schema()
        db.initialize_database()
        rows = db.execute("SELECT COUNT(*) FROM sites")[0][0]
        self.assertEqual(rows, 1)
        bonus_count = db.execute("SELECT COUNT(*) FROM bonuses")[0][0]
        self.assertEqual(bonus_count, 1)

    def test_initialize_database_migrates_legacy_file(self):
        db.initialize_database()
        url = db.execute("SELECT url FROM sites WHERE error_code=200")[0][0]
        self.assertEqual(url, "https://example.test/a")


if __name__ == "__main__":
    unittest.main()
