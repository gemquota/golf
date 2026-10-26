import unittest

from bonus_scoring import score_bonus


class BonusScoringTests(unittest.TestCase):
    def test_v2_caps_advertised_amount_at_maximum_bonus(self):
        score = score_bonus(1000, minwithdraw=50, maxwithdraw=100, rollover=1)
        capped = score_bonus(100, minwithdraw=50, maxwithdraw=100, rollover=1)
        self.assertLess(score["weighted_score"], score["weighted_score_v1"])
        self.assertAlmostEqual(score["weighted_score"], capped["weighted_score"])

    def test_higher_rollover_reduces_score(self):
        easy = score_bonus(100, minwithdraw=50, maxwithdraw=200, rollover=1)
        hard = score_bonus(100, minwithdraw=50, maxwithdraw=200, rollover=20)
        self.assertGreater(easy["weighted_score"], hard["weighted_score"])

    def test_rollover_penalty_is_normalized_by_bonus_amount(self):
        small = score_bonus(100, minwithdraw=50, maxwithdraw=200, rollover=500)
        scaled = score_bonus(200, minwithdraw=50, maxwithdraw=200, rollover=1000)
        self.assertAlmostEqual(
            small["weighted_score"] / scaled["weighted_score"],
            0.5,
        )

    def test_unreachable_cashout_threshold_is_penalised(self):
        reachable = score_bonus(100, minwithdraw=50, maxwithdraw=200, rollover=2)
        unreachable = score_bonus(100, minwithdraw=100, maxwithdraw=20, rollover=2)
        self.assertLess(unreachable["weighted_score"], reachable["weighted_score"])

    def test_missing_max_uses_site_median_and_marks_estimated(self):
        score = score_bonus(100, minwithdraw=50, maxwithdraw=None, rollover=2,
                            site_maxwithdraw=250, global_maxwithdraw=300)
        self.assertEqual(score["score_maxwithdraw_source"], "site_median")
        self.assertEqual(score["score_confidence"], "medium")
        self.assertGreater(score["weighted_score"], 0)

    def test_missing_rollover_is_not_treated_as_zero(self):
        score = score_bonus(100, minwithdraw=50, maxwithdraw=250)
        self.assertIsNone(score["weighted_score"])
        self.assertEqual(score["score_confidence"], "low")
        self.assertEqual(score["score_status"], "provisional_missing_rollover")

    def test_minimum_fallback_is_explicit(self):
        score = score_bonus(100, minwithdraw=None, site_minwithdraw=None,
                            maxwithdraw=250, rollover=2)
        self.assertEqual(score["effective_minwithdraw"], 50)
        self.assertEqual(score["score_confidence"], "low")
        self.assertEqual(score["score_status"], "estimated")

    def test_burden_metric_is_preserved_separately(self):
        score = score_bonus(100, minwithdraw=50, maxwithdraw=250, rollover=5)
        self.assertAlmostEqual(score["rollover_ratio_average"], 0.6 * 5 + 0.4 * 0.5)
        self.assertNotEqual(score["rollover_ratio_average"], score["weighted_score"])


if __name__ == "__main__":
    unittest.main()
