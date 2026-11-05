# Bonus scoring

The enriched export retains **Perceived Value** and adds:

- `weighted_score_v1`: legacy benefit-only score, `(amount / effective_minwithdraw) * sqrt(maxwithdraw)`.
- `weighted_score` (viewer label **Weighted v2**): higher is better. It caps credited bonus at maximum payout, penalizes an unreachable minimum withdrawal, and applies a normalized rollover penalty.
- `rollover_ratio_average`: separate 60:40 burden metric, `0.60 * rollover + 0.40 * (effective_minwithdraw / amount)`. Lower is better.

For advertised bonus A, effective minimum withdrawal M, maximum payout X, and wagering multiplier R:

`min(A, X) / M * sqrt(X) * min(1, X / M) / (1 + 0.20 * (R / A))`

The coefficient is a tunable heuristic, not a calibrated probability or expected-profit estimate.

## Missing data and confidence

Minimum withdrawal falls back from offer value to site configuration to explicit default 50. Maximum payout falls back from observed value to same-site median, dataset median, then legacy default 3776. Rollover falls back from observed value to same-site or dataset median. If no rollover evidence exists, v2 remains blank, never zero. Confidence and source columns disclose imputation. The 3776 fallback is not verified offer data.

Run `python -m unittest tests.test_bonus_scoring` or `python -m unittest discover -s tests -v`.
