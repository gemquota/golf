import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import db


class SQLiteThreadSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        self.original_cache = db._cache
        db.DB_PATH = str(Path(self.temp_dir.name) / "thread-safety.sqlite")
        db._cache = {}
        db.execute("CREATE TABLE t (u TEXT PRIMARY KEY)")

    def tearDown(self):
        for connection in db._cache.values():
            connection.close()
        db.DB_PATH = self.original_db_path
        db._cache = self.original_cache
        self.temp_dir.cleanup()

    def test_concurrent_workers_can_insert_and_read_without_sqlite_api_errors(self):
        def insert_and_read(index):
            url = f"https://example.test/{index}"
            db.execute("INSERT OR IGNORE INTO t(u) VALUES (?)", (url,))
            return db.execute("SELECT u FROM t WHERE u=?", (url,))[0][0]

        with ThreadPoolExecutor(max_workers=16) as executor:
            results = list(executor.map(insert_and_read, range(500)))

        self.assertEqual(len(results), 500)
        self.assertEqual(len(set(results)), 500)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM t")[0][0], 500)


if __name__ == "__main__":
    unittest.main()
