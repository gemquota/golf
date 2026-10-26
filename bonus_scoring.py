"""Transparent bonus scoring helpers.

The rollover field is treated as a wagering multiplier, not a currency amount.
Higher weighted scores are better; rollover_ratio_average remains a separate
burden metric where lower is better.
"""
from math import isfinite, sqrt

DEFAULT_MIN_WITHDRAW = 50.0
DEFAULT_MAX_WITHDRAW = 3776.0
ROLLOVER_PENALTY = 0.20


def number(value):
    try:
        value = float(value)
        return value if isfinite(value) else None
    except (TypeError, ValueError):
        return None


def score_bonus(
    amount,
    minwithdraw=None,
    site_minwithdraw=None,
    maxwithdraw=None,
    rollover=None,
    site_maxwithdraw=None,
    site_rollover=None,
    global_maxwithdraw=None,
    global_rollover=None,
):
    """Return score components, provenance and confidence for one bonus.

    Missing maximum withdrawal is imputed in order: same-site median, dataset
    median, then DEFAULT_MAX_WITHDRAW. Missing rollover is imputed from the
    same-site median then dataset median. If no rollover evidence exists, the
    score remains blank instead of pretending unknown rollover is zero.
    """
    amount = number(amount)
    minimum = number(minwithdraw)
    site_minimum = number(site_minwithdraw)
    maximum = number(maxwithdraw)
    roll = number(rollover)
    sources = []

    if amount is None or amount <= 0:
        return {
            "effective_minwithdraw": None, "score_maxwithdraw_used": None,
            "score_rollover_used": None, "weighted_score_v1": None,
            "weighted_score": None, "rollover_ratio_average": None,
            "score_confidence": "none", "score_status": "invalid_amount",
            "score_maxwithdraw_source": "missing", "score_rollover_source": "missing",
        }

    if minimum is not None and minimum > 0:
        effective_min, min_source = minimum, "bonus"
    elif site_minimum is not None and site_minimum > 0:
        effective_min, min_source = site_minimum, "site"
        sources.append("site_minimum")
    else:
        effective_min, min_source = DEFAULT_MIN_WITHDRAW, "default_50"
        sources.append("default_minimum")

    if maximum is not None and maximum > 0:
        max_source = "observed"
    elif number(site_maxwithdraw) and number(site_maxwithdraw) > 0:
        maximum, max_source = number(site_maxwithdraw), "site_median"
        sources.append("site_maxwithdraw")
    elif number(global_maxwithdraw) and number(global_maxwithdraw) > 0:
        maximum, max_source = number(global_maxwithdraw), "dataset_median"
        sources.append("dataset_maxwithdraw")
    else:
        maximum, max_source = DEFAULT_MAX_WITHDRAW, "default_3776"
        sources.append("default_maxwithdraw")

    if roll is not None and roll >= 0:
        roll_source = "observed"
    elif number(site_rollover) is not None and number(site_rollover) >= 0:
        roll, roll_source = number(site_rollover), "site_median"
        sources.append("site_rollover")
    elif number(global_rollover) is not None and number(global_rollover) >= 0:
        roll, roll_source = number(global_rollover), "dataset_median"
        sources.append("dataset_rollover")
    else:
        roll, roll_source = None, "missing"

    # The legacy benefit-only formula is retained for a fair side-by-side test.
    score_v1 = (amount / effective_min) * sqrt(maximum) if maximum > 0 else None

    # V2 caps the credited bonus at the maximum payout, adds a withdrawal
    # feasibility factor, and penalises the wagering multiplier.
    if roll is not None:
        usable_bonus = min(amount, maximum)
        cashout_feasibility = min(1.0, maximum / effective_min)
        score_v2 = (
            (usable_bonus / effective_min)
            * sqrt(maximum)
            * cashout_feasibility
            / (1.0 + ROLLOVER_PENALTY * (roll / amount))
        )
    else:
        score_v2 = None

    ratio = effective_min / amount
    burden = (0.60 * roll + 0.40 * ratio) if roll is not None else None

    if not sources:
        confidence = "high"
        status = "observed"
    elif "default_maxwithdraw" in sources or "default_minimum" in sources:
        confidence = "low"
        status = "estimated"
    elif "dataset_maxwithdraw" in sources or "dataset_rollover" in sources:
        confidence = "low"
        status = "estimated"
    else:
        confidence = "medium"
        status = "estimated"

    if roll is None:
        confidence = "low"
        status = "provisional_missing_rollover"

    return {
        "effective_minwithdraw": effective_min,
        "score_maxwithdraw_used": maximum,
        "score_rollover_used": roll,
        "weighted_score_v1": score_v1,
        "weighted_score": score_v2,
        "rollover_ratio_average": burden,
        "score_confidence": confidence,
        "score_status": status,
        "score_maxwithdraw_source": max_source,
        "score_rollover_source": roll_source,
    }
