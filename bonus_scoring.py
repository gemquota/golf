"""Transparent bonus scoring helpers. Unknown rollover is never treated as zero."""
from math import isfinite, sqrt

DEFAULT_MIN_WITHDRAW = 50.0
DEFAULT_MAX_WITHDRAW = 3776.0
ROLLOVER_PENALTY = 0.20


def number(value):
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (TypeError, ValueError):
        return None


def score_bonus(amount, minwithdraw=None, site_minwithdraw=None, maxwithdraw=None,
                rollover=None, site_maxwithdraw=None, site_rollover=None,
                global_maxwithdraw=None, global_rollover=None):
    amount, minimum = number(amount), number(minwithdraw)
    site_minimum, maximum, roll = number(site_minwithdraw), number(maxwithdraw), number(rollover)
    estimated = []
    if amount is None or amount <= 0:
        return {"effective_minwithdraw": None, "score_maxwithdraw_used": None,
                "score_rollover_used": None, "weighted_score_v1": None,
                "weighted_score": None, "rollover_ratio_average": None,
                "score_confidence": "none", "score_status": "invalid_amount",
                "score_maxwithdraw_source": "missing", "score_rollover_source": "missing"}
    if minimum is not None and minimum > 0:
        effective_min = minimum
    elif site_minimum is not None and site_minimum > 0:
        effective_min = site_minimum; estimated.append("site_minimum")
    else:
        effective_min = DEFAULT_MIN_WITHDRAW; estimated.append("default_minimum")
    if maximum is not None and maximum > 0:
        max_source = "observed"
    elif number(site_maxwithdraw) is not None and number(site_maxwithdraw) > 0:
        maximum = number(site_maxwithdraw); max_source = "site_median"; estimated.append("site_maxwithdraw")
    elif number(global_maxwithdraw) is not None and number(global_maxwithdraw) > 0:
        maximum = number(global_maxwithdraw); max_source = "dataset_median"; estimated.append("dataset_maxwithdraw")
    else:
        maximum = DEFAULT_MAX_WITHDRAW; max_source = "default_3776"; estimated.append("default_maxwithdraw")
    if roll is not None and roll >= 0:
        roll_source = "observed"
    elif number(site_rollover) is not None and number(site_rollover) >= 0:
        roll = number(site_rollover); roll_source = "site_median"; estimated.append("site_rollover")
    elif number(global_rollover) is not None and number(global_rollover) >= 0:
        roll = number(global_rollover); roll_source = "dataset_median"; estimated.append("dataset_rollover")
    else:
        roll = None; roll_source = "missing"
    score_v1 = amount / effective_min * sqrt(maximum) if maximum > 0 else None
    score_v2 = None
    if roll is not None:
        score_v2 = (min(amount, maximum) / effective_min * sqrt(maximum)
                    * min(1.0, maximum / effective_min)
                    / (1.0 + ROLLOVER_PENALTY * (roll / amount)))
    burden = 0.60 * roll + 0.40 * (effective_min / amount) if roll is not None else None
    if roll is None:
        confidence, status = "low", "provisional_missing_rollover"
    elif any(x in estimated for x in ("default_minimum", "default_maxwithdraw",
                                      "dataset_maxwithdraw", "dataset_rollover")):
        confidence, status = "low", "estimated"
    elif estimated:
        confidence, status = "medium", "estimated"
    else:
        confidence, status = "high", "observed"
    return {"effective_minwithdraw": effective_min, "score_maxwithdraw_used": maximum,
            "score_rollover_used": roll, "weighted_score_v1": score_v1,
            "weighted_score": score_v2, "rollover_ratio_average": burden,
            "score_confidence": confidence, "score_status": status,
            "score_maxwithdraw_source": max_source, "score_rollover_source": roll_source}
