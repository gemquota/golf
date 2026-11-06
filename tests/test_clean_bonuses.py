import csv
import tempfile
import unittest
from pathlib import Path

from clean_bonuses import clean_bonuses, write_cleaned_csv


class CleanBonusesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "input.csv"

    def tearDown(self):
        self.temp.cleanup()

    def write_rows(self, fields, rows):
        with self.source.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_standard_library_cleaner_preserves_v2_score_and_legacy_filtering(self):
        fields = [
            "url", "name", "amount", "minwithdraw", "site_minwithdraw",
            "maxwithdraw", "rollover", "perceived_value", "weighted_score",
            "weighted_score_v1", "id", "transactiontype", "bonusfixed", "balance",
        ]
        rows = [
            {"url":"https://a.test","name":"A","amount":"100","minwithdraw":"25","site_minwithdraw":"40","maxwithdraw":"100","rollover":"2","perceived_value":"50","weighted_score":"8","weighted_score_v1":"7","id":"1","transactiontype":"x","bonusfixed":"1","balance":"9"},
            {"url":"https://a.test","name":"A","amount":"100","minwithdraw":"25","site_minwithdraw":"40","maxwithdraw":"100","rollover":"2","perceived_value":"50","weighted_score":"8","weighted_score_v1":"7","id":"2","transactiontype":"x","bonusfixed":"1","balance":"9"},
            {"url":"https://b.test","name":"B","amount":"50","minwithdraw":"","site_minwithdraw":"60","maxwithdraw":"100","rollover":"","perceived_value":"50","weighted_score":"4","weighted_score_v1":"3"},
            {"url":"https://c.test","name":"C","amount":"100","minwithdraw":"","site_minwithdraw":"","maxwithdraw":"100","rollover":"0","perceived_value":"30","weighted_score":"","weighted_score_v1":"1"},
            {"url":"https://d.test","name":"D","amount":"100","minwithdraw":"60000","maxwithdraw":"100","rollover":"2","perceived_value":"1","weighted_score":"1","weighted_score_v1":"1"},
            {"url":"https://bad.test","name":"bad","amount":"not-a-number","maxwithdraw":"100"},
        ]
        self.write_rows(fields, rows)
        output_fields, cleaned = clean_bonuses(self.source)

        self.assertEqual(len(cleaned), 3)
        self.assertEqual([row["name"] for row in cleaned], ["A", "B", "C"])
        self.assertEqual(cleaned[0]["effective_minwithdraw"], 25)
        self.assertEqual(cleaned[0]["ratio"], 0.25)
        self.assertEqual(cleaned[0]["rollover_ratio_average"], 1.3)
        self.assertEqual(cleaned[0]["weighted_score"], 8)
        self.assertEqual(cleaned[0]["perceived_value_rank"], 1)
        self.assertEqual(cleaned[1]["perceived_value_rank"], 1)
        self.assertEqual(cleaned[2]["weighted_score_rank"], 5)
        self.assertNotIn("id", output_fields)
        self.assertNotIn("transactiontype", output_fields)

        destination = self.root / "cleaned.csv"
        write_cleaned_csv(output_fields, cleaned, destination)
        with destination.open(newline="", encoding="utf-8") as stream:
            written = list(csv.DictReader(stream))
        self.assertEqual(len(written), 3)
        self.assertEqual(written[0]["name"], "A")

    def test_legacy_input_uses_historical_fallback_score(self):
        self.write_rows(
            ["url", "name", "amount", "minwithdraw", "maxwithdraw", "rollover"],
            [{"url":"https://legacy.test","name":"Legacy","amount":"100","minwithdraw":"50","maxwithdraw":"100","rollover":"2"}],
        )
        fields, rows = clean_bonuses(self.source)
        self.assertEqual(rows[0]["weighted_score"], 20.0)
        self.assertIn("weighted_score", fields)

    def test_missing_amount_column_fails_with_clear_message(self):
        self.write_rows(["url", "name"], [{"url":"https://x.test","name":"X"}])
        with self.assertRaisesRegex(ValueError, "amount column"):
            clean_bonuses(self.source)


if __name__ == "__main__":
    unittest.main()
