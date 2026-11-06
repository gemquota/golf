import configparser
import io
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts.audit_db_security import inspect_config, inspect_database, main


class DatabaseSecurityAuditTests(unittest.TestCase):
    def test_audit_counts_payloads_without_returning_values_and_scrubs_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "base.db"
            connection = sqlite3.connect(path)
            connection.execute(
                "CREATE TABLE sessions (user_id TEXT, url TEXT, cookies BLOB, session_data BLOB)"
            )
            connection.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?)",
                ("account", "https://example.test", b"COOKIE_SECRET", b"SESSION_SECRET"),
            )
            connection.commit()
            connection.close()

            result = inspect_database(path, scrub=True)

            self.assertEqual(result["session_rows"], 1)
            self.assertEqual(result["cookie_rows"], 1)
            self.assertEqual(result["session_data_rows"], 1)
            self.assertEqual(result["remaining_rows"], 0)
            self.assertNotIn("COOKIE_SECRET", repr(result))
            self.assertNotIn("SESSION_SECRET", repr(result))

    def test_audit_supports_legacy_session_table_names(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.db"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE s (uid TEXT, u TEXT, ck BLOB, data BLOB)")
            connection.execute("INSERT INTO s VALUES ('u1', 'https://example.test', 'cookie', 'data')")
            connection.commit()
            connection.close()

            result = inspect_database(path)
            self.assertEqual(result["session_rows"], 1)
            self.assertEqual(result["cookie_rows"], 1)
            self.assertEqual(result["session_data_rows"], 1)

    def test_config_audit_reports_only_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.ini"
            path.write_text(
                "[U1]\\nu = ACCOUNT_SECRET\\np = PASSWORD_SECRET\\n"
                "[U2]\\nu =\\np =\\n",
                encoding="utf-8",
            )
            result = inspect_config(path)
            self.assertEqual(result["account_sections"], 2)
            self.assertEqual(result["populated_user_fields"], 1)
            self.assertEqual(result["populated_password_fields"], 1)
            self.assertNotIn("PASSWORD_SECRET", repr(result))


if __name__ == "__main__":
    unittest.main()
