import unittest
from bonus_scoring import score_bonus


class BonusScoringTests(unittest.TestCase):
    def test_caps_advertised_amount(self):
        high = score_bonus(1000, 50, maxwithdraw=100, rollover=10)
        capped = score_bonus(100, 50, maxwithdraw=100, rollover=1)
        self.assertLess(high["weighted_score"], high["weighted_score_v1"])
        self.assertAlmostEqual(high["weighted_score"], capped["weighted_score"])

    def test_rollover_reduces_score(self):
        easy = score_bonus(100, 50, maxwithdraw=200, rollover=1)
        hard = score_bonus(100, 50, maxwithdraw=200, rollover=20)
        self.assertGreater(easy["weighted_score"], hard["weighted_score"])

    def test_rollover_is_normalized_by_amount(self):
        a = score_bonus(100, 50, maxwithdraw=200, rollover=500)["weighted_score"]
        b = score_bonus(200, 50, maxwithdraw=200, rollover=1000)["weighted_score"]
        self.assertAlmostEqual(a / b, 0.5)

    def test_unreachable_minimum_penalized(self):
        reachable = score_bonus(100, 50, maxwithdraw=200, rollover=2)
        unreachable = score_bonus(100, 100, maxwithdraw=20, rollover=2)
        self.assertLess(unreachable["weighted_score"], reachable["weighted_score"])

    def test_site_median_imputation(self):
        result = score_bonus(100, 50, maxwithdraw=None, rollover=2, site_maxwithdraw=250)
        self.assertEqual(result["score_maxwithdraw_source"], "site_median")
        self.assertEqual(result["score_confidence"], "medium")

    def test_missing_rollover_is_not_zero(self):
        result = score_bonus(100, 50, maxwithdraw=250)
        self.assertIsNone(result["weighted_score"])
        self.assertEqual(result["score_status"], "provisional_missing_rollover")

    def test_minimum_default_is_explicit(self):
        result = score_bonus(100, maxwithdraw=250, rollover=2)
        self.assertEqual(result["effective_minwithdraw"], 50)
        self.assertEqual(result["score_confidence"], "low")

    def test_burden_is_separate(self):
        result = score_bonus(100, 50, maxwithdraw=250, rollover=5)
        self.assertAlmostEqual(result["rollover_ratio_average"], 0.6 * 5 + 0.4 * 0.5)
        self.assertNotEqual(result["rollover_ratio_average"], result["weighted_score"])


if ( __name__ == "__main__"):
    unittest.main()
