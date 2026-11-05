import unittest
from datetime import date

import bonus_history


class BonusHistoryTests(unittest.TestCase):
    def test_commission_detection(self):
        self.assertTrue(bonus_history.is_commission({"name": "Weekly Commission"}))
        self.assertTrue(bonus_history.is_commission({"name": "Downline rebate"}))
        self.assertFalse(bonus_history.is_commission({"name": "Welcome bonus"}))

    def test_bonus_identity_is_stable_when_value_changes(self):
        url = "https://example.test"
        first = {"id": "123", "name": "Weekly commission", "amount": 10}
        changed = {"id": "123", "name": "Weekly commission", "amount": 20}
        self.assertEqual(bonus_history.bonus_key(url, first), bonus_history.bonus_key(url, changed))
        self.assertNotEqual(bonus_history.signature(first), bonus_history.signature(changed))

    def test_name_fallback_identity_is_stable_when_amount_changes(self):
        url = "https://example.test"
        first = {"name": "Weekly commission", "amount": 10}
        changed = {"name": "Weekly commission", "amount": 20}
        self.assertEqual(bonus_history.bonus_key(url, first), bonus_history.bonus_key(url, changed))

    def test_analytics_counts_commissions_by_weekday(self):
        monday = date(2026, 10, 19).isoformat()
        friday = date(2026, 10, 23).isoformat()
        events = [
            {"type": "new_commission", "date": monday, "url": "https://a.test",
             "merchant": "A", "key": "1", "bonus": {"name": "Commission", "amount": 10}},
            {"type": "new_commission", "date": friday, "url": "https://a.test",
             "merchant": "A", "key": "2", "bonus": {"name": "Commission", "amount": 20}},
            {"type": "new_bonus", "date": friday, "url": "https://a.test",
             "merchant": "A", "key": "3", "bonus": {"name": "Welcome bonus", "amount": 30}},
        ]
        result = bonus_history.build_analytics(events, [], "now", {
            "https://a.test": {"merchant": "A", "observed_days": 2}
        })
        counts = {row["weekday"]: row["count"] for row in result["weekday_releases"]}
        self.assertEqual(counts["Monday"], 1)
        self.assertEqual(counts["Friday"], 1)
        self.assertEqual(result["release_count"], 2)

    def test_first_baseline_can_be_stored_without_release_classification(self):
        baseline = {"key": "k", "name": "Weekly commission", "amount": 10,
                    "is_commission": True}
        compact = bonus_history.compact_bonus(baseline)
        self.assertEqual(compact["key"], "k")
        self.assertTrue(compact["is_commission"])

    def test_attempt_loader_uses_canonical_sites_schema(self):
        import sqlite3
        connection = sqlite3.connect(":memory:")
        connection.execute(
            "CREATE TABLE sites (url TEXT, merchant_name TEXT, updated_at TEXT, error_code INTEGER)"
        )
        connection.executemany(
            "INSERT INTO sites VALUES (?, ?, ?, ?)",
            [
                ("https://success.example", "Success", "2026-11-06 01:00:00", 200),
                ("https://blocked.example", "Blocked", "2026-11-06 01:05:00", 403),
                ("https://old.example", "Old", "2026-11-05 23:00:00", 200),
            ],
        )
        attempts = bonus_history.load_attempts(connection, "2026-11-06 00:00:00")
        self.assertEqual(set(attempts), {
            "https://success.example", "https://blocked.example"
        })
        self.assertEqual(attempts["https://success.example"]["status"], "success")
        self.assertEqual(attempts["https://blocked.example"]["status"], "failed")
        self.assertEqual(attempts["https://blocked.example"]["error_code"], 403)
        connection.close()


if __name__ == "__main__":
    unittest.main()
