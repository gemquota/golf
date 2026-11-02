"""Network-free smoke tests for each CLI subcommand."""
import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import db
from golf import cli


def _stub_heavy_modules():
    """Avoid requiring fastapi/cloudscraper for CLI smoke tests."""
    stubs = {}
    if "server" not in sys.modules:
        server = types.ModuleType("server")
        server.STOPPED = False
        server.PAUSED = False
        server.IS_RUNNING = False
        server.start_server = MagicMock()
        stubs["server"] = server
        sys.modules["server"] = server
    if "scraper" not in sys.modules:
        scraper = types.ModuleType("scraper")
        scraper.run_scrape = MagicMock()
        stubs["scraper"] = scraper
        sys.modules["scraper"] = scraper
    if "terminal" not in sys.modules:
        terminal = types.ModuleType("terminal")
        terminal.update_display = MagicMock()
        terminal.print_launcher = MagicMock()
        terminal.print_completion = MagicMock()
        stubs["terminal"] = terminal
        sys.modules["terminal"] = terminal
    if "fastapi" not in sys.modules:
        sys.modules["fastapi"] = types.ModuleType("fastapi")
    return stubs


class CliSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        self.db_path = self.root / "data" / "base.db"
        self.original_db_path = db.DB_PATH
        self.original_cache = db._cache
        self.original_root = cli.ROOT
        db.DB_PATH = str(self.db_path)
        db._cache = {}
        cli.ROOT = self.root
        _stub_heavy_modules()

    def tearDown(self):
        for connection in list(db._cache.values()):
            connection.close()
        db.DB_PATH = self.original_db_path
        db._cache = self.original_cache
        cli.ROOT = self.original_root
        self.temp.cleanup()

    def test_parser_exposes_required_subcommands(self):
        parser = cli.build_parser()
        action = next(a for a in parser._actions if getattr(a, "dest", None) == "command")
        self.assertTrue({"run", "scrape", "interactive", "export", "migrate"} <= set(action.choices))

    def test_migrate_subcommand(self):
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE t (u TEXT PRIMARY KEY, ec INTEGER, ts DATETIME)")
        conn.execute("INSERT INTO t(u,ec,ts) VALUES ('https://x.test',200,'2026-01-01 00:00:00')")
        conn.commit()
        conn.close()

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(["migrate"])
        self.assertEqual(rc, 0)
        self.assertIn("Migration complete", buf.getvalue())
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        self.assertIn("sites", tables)
        self.assertNotIn("t", tables)

    def test_export_subcommand_empty_db(self):
        db.initialize_database()
        with patch.object(cli, "run_stage") as run_stage:
            rc = cli.main(["export"])
        self.assertEqual(rc, 0)
        run_stage.assert_not_called()

    def test_export_viewer_flag_invokes_stage(self):
        db.initialize_database()
        with patch.object(cli, "run_stage") as run_stage:
            rc = cli.main(["export", "--viewer"])
        self.assertEqual(rc, 0)
        run_stage.assert_called_once()
        self.assertEqual(run_stage.call_args.args[0], "export_viewer_data.py")

    def test_pipeline_subcommand_invokes_maintain(self):
        db.initialize_database()
        with patch("maintain_pipeline.run_pipeline") as run_pipeline, \
             patch.object(cli, "run_stage") as run_stage:
            rc = cli.main(["pipeline", "--no-publish"])
        self.assertEqual(rc, 0)
        run_pipeline.assert_called_once()
        self.assertEqual(run_stage.call_count, 1)
        self.assertEqual(run_stage.call_args.args[0], "build_exports.py")

    def test_scrape_and_run_accept_flags_without_network(self):
        db.initialize_database()
        import scraper
        for sub in ("scrape", "run"):
            scraper.run_scrape = MagicMock()

            def fake_scrape(on_update=None, on_launcher=None, on_completion=None):
                if on_completion:
                    on_completion({
                        "successes": 0, "failures": 0,
                        "total_bonuses": 0, "new_bonuses": 0,
                    })

            scraper.run_scrape.side_effect = fake_scrape
            with patch.object(cli, "run_stage"):
                rc = cli.main([sub, "--no-pipeline", "--no-publish"])
            self.assertEqual(rc, 0, sub)
            self.assertTrue(scraper.run_scrape.called)

    def test_interactive_wires_scraper_thread_and_server(self):
        db.initialize_database()
        import scraper
        import server
        scraper.run_scrape = MagicMock()
        server.start_server = MagicMock()
        with patch("threading.Thread") as thread_cls:
            thread = thread_cls.return_value
            rc = cli.main(["interactive", "--no-pipeline"])
        self.assertEqual(rc, 0)
        thread_cls.assert_called_once()
        thread.start.assert_called_once()
        server.start_server.assert_called_once()
        self.assertEqual(thread_cls.call_args.kwargs.get("target"), scraper.run_scrape)


if __name__ == "__main__":
    unittest.main()
