import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scraper


class AccountStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.state = root / "account_state.json"
        self.legacy = root / "account_success.json"
        self.probes = root / "probe_attempts.csv"
        self.patches = patch.multiple(
            scraper,
            ACCOUNT_STATE=self.state,
            ACCOUNT_SUCCESS=self.legacy,
            PROBE_ATTEMPTS_CSV=self.probes,
        )
        self.patches.start()
        scraper.CURRENT_RUN_ID = "test-run"

    def tearDown(self):
        self.patches.stop()
        self.temp.cleanup()

    def test_later_success_recovers_unregistered_state_and_preserves_transition(self):
        scraper.record_account_discovery_result("https://example.test", [304, 304, 304])
        before = json.loads(self.state.read_text())
        self.assertEqual(before["https://example.test"]["status"], "unregistered")
        self.assertIsNone(before["https://example.test"].get("verified_at"))
        self.assertTrue(before["https://example.test"]["classified_at"])

        scraper.record_account_success("https://example.test", "U2")
        after = json.loads(self.state.read_text())["https://example.test"]
        self.assertEqual(after["status"], "registered")
        self.assertEqual(after["account_id"], "U2")
        self.assertEqual(after["transitions"][-1]["from"], "unregistered")
        self.assertEqual(after["transitions"][-1]["to"], "registered")
        self.assertEqual(scraper.load_account_successes()["https://example.test"], "U2")
        self.assertFalse(self.legacy.exists())

    def test_legacy_mapping_is_merged_but_canonical_state_wins(self):
        self.legacy.write_text(json.dumps({
            "https://legacy.test": "U1",
            "https://example.test": "U1",
        }))
        self.state.write_text(json.dumps({
            "https://example.test": {"status": "registered", "account_id": "U3"}
        }))
        loaded = scraper.load_account_successes()
        self.assertEqual(loaded["https://legacy.test"], "U1")
        self.assertEqual(loaded["https://example.test"], "U3")

    def test_probe_attempt_ledger_records_account_and_error_namespace(self):
        scraper.record_probe_attempt(
            "https://example.test", "U2", 2, "authentication_rejected",
            304, RuntimeError("credential rejected"),
        )
        with self.probes.open(newline="") as stream:
            row = next(csv.DictReader(stream))
        self.assertEqual(row["run_id"], "test-run")
        self.assertEqual(row["account_id"], "U2")
        self.assertEqual(row["attempt_number"], "2")
        self.assertEqual(row["error_code"], "304")
        self.assertEqual(row["outcome"], "authentication_rejected")


if __name__ == "__main__":
    unittest.main()
