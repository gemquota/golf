import unittest

from promo_discovery import _candidate_links, extract_fields


class PromotionExtractionTests(unittest.TestCase):
    def test_zero_value_welcome_offer_is_still_discovered(self):
        fields = extract_fields(
            "Welcome bonus: 0 AUD bonus. New customers receive a 100% first deposit bonus."
        )
        self.assertIn("welcome bonus", fields["matched_terms"])
        self.assertIn("first deposit bonus", fields["matched_terms"])
        self.assertEqual(fields["bonus_percentage"], "100%")

    def test_extracts_percentage_maximum_payout_and_turnover(self):
        fields = extract_fields(
            "Sign up bonus 200% up to $500 maximum payout. "
            "First deposit bonus requires 35x wagering."
        )
        self.assertEqual(fields["bonus_percentage"], "200%")
        self.assertEqual(fields["max_payout"], "AUD 500")
        self.assertEqual(fields["rollover_requirement"], "35x")

    def test_does_not_treat_unrelated_rtp_percentage_as_bonus_percentage(self):
        fields = extract_fields(
            "Welcome bonus available. Games have 96.5% RTP and a 100% deposit match."
        )
        self.assertEqual(fields["bonus_percentage"], "100%")

    def test_promotion_links_are_same_origin_and_filtered(self):
        links = [
            ("/promotions", "Promotions"),
            ("https://elsewhere.example/welcome", "Welcome bonus"),
            ("/terms", "Terms"),
            ("/offers/first-deposit", "First deposit offer"),
        ]
        self.assertEqual(
            _candidate_links("https://merchant.example/", links),
            [
                "https://merchant.example/promotions",
                "https://merchant.example/offers/first-deposit",
            ],
        )


if __name__ == "__main__":
    unittest.main()
