import unittest

from bonus_scoring import score_bonus
from export_csv import build_scoring_context, normalize_bonus_json, score_bonus_row


class SharedExportPipelineTests(unittest.TestCase):
    def test_normalize_bonus_json_handles_invalid_and_non_object_payloads(self):
        self.assertEqual(normalize_bonus_json("{"), {})
        self.assertEqual(normalize_bonus_json("[]"), {})
        self.assertEqual(normalize_bonus_json('{"MaxWithdraw": 250}'), {"maxwithdraw": 250})

    def test_scoring_context_uses_site_and_dataset_medians(self):
        rows = [
            {"url": "https://a.example", "raw_json": '{"maxwithdraw": 100, "rollover": 2}'},
            {"url": "https://a.example", "raw_json": '{"maxwithdraw": 300, "rollover": 4}'},
            {"url": "https://b.example", "raw_json": '{"maxwithdraw": 500, "rollover": 8}'},
            {"url": "https://c.example", "raw_json": '{"maxwithdraw": 0, "rollover": -1}'},
        ]
        context = build_scoring_context(rows)
        self.assertEqual(context["site_maxwithdraw"]["a.example"], 200)
        self.assertEqual(context["site_rollover"]["a.example"], 3)
        self.assertEqual(context["global_maxwithdraw"], 300)
        self.assertEqual(context["global_rollover"], 4)

    def test_shared_row_scoring_matches_canonical_policy(self):
        row = {
            "url": "https://a.example",
            "amount": 100,
            "raw_json": '{"minwithdraw": 50, "maxwithdraw": 200, "rollover": 2}',
        }
        context = build_scoring_context([row])
        actual = score_bonus_row(row, normalize_bonus_json(row["raw_json"]), {}, context)
        expected = score_bonus(100, 50, None, 200, 2, 200, 2, 200, 2)
        self.assertEqual(actual, expected)

    def test_shared_row_scoring_uses_database_amount_when_override_is_supplied(self):
        row = {
            "url": "https://a.example",
            "amount": 80,
            "raw_json": '{"amount": 120, "minwithdraw": 40, "maxwithdraw": 200, "rollover": 2}',
        }
        normalized = normalize_bonus_json(row["raw_json"])
        normalized["amount"] = row["amount"]
        context = build_scoring_context([row])
        actual = score_bonus_row(row, normalized, {}, context)
        expected = score_bonus(80, 40, None, 200, 2, 200, 2, 200, 2)
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
