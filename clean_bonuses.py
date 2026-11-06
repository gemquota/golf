"""Standard-library CSV cleaner for legacy bonus snapshots.

The canonical score is preserved when present. Older CSVs without a v2 score
retain the historical benefit-only fallback so existing files remain usable.
"""
import csv
import sys
from math import sqrt
from pathlib import Path

from bonus_scoring import number


DROP_COLUMNS = {"id", "transactiontype", "bonusfixed", "balance"}
NUMERIC_COLUMNS = {
    "amount", "minwithdraw", "site_minwithdraw", "effective_minwithdraw",
    "maxwithdraw", "rollover", "ratio", "perceived_value", "weighted_score",
}


def _rank_desc_min(values):
    """Pandas-compatible descending rank(method='min', na_option='bottom')."""
    valid = sorted((value for value in values if value is not None), reverse=True)
    ranks = {}
    for index, value in enumerate(valid, start=1):
        ranks.setdefault(value, index)
    missing_rank = len(valid) + 1
    return [ranks.get(value, missing_rank) for value in values]


def clean_bonuses(csv_file):
    """Return (output fieldnames, cleaned rows) without third-party dependencies."""
    with Path(csv_file).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        source_fields = list(reader.fieldnames or [])
        if "amount" not in source_fields:
            raise ValueError("Input CSV must contain an amount column")
        rows = []
        for source in reader:
            row = dict(source)
            amount = number(row.get("amount"))
            if amount is None or amount <= 0:
                continue
            row["amount"] = amount
            for field in NUMERIC_COLUMNS.intersection(row):
                if field != "amount":
                    row[field] = number(row.get(field))

            for field in DROP_COLUMNS:
                row.pop(field, None)

            bonus_min = number(row.get("minwithdraw"))
            site_min = number(row.get("site_minwithdraw"))
            effective_min = bonus_min if bonus_min is not None and bonus_min > 0 else site_min
            if effective_min is None or effective_min <= 0:
                effective_min = 50.0
            ratio = round(effective_min / amount, 4)

            rollover = number(row.get("rollover"))
            burden = round(rollover * 0.60 + ratio * 0.40, 4) if rollover is not None else None

            # Exported v2 scores remain authoritative. Older files retain the
            # original benefit-only fallback instead of silently changing rank.
            if "weighted_score_v1" not in source_fields:
                maximum = number(row.get("maxwithdraw"))
                score = (
                    round((amount / effective_min) * sqrt(maximum), 4)
                    if maximum is not None and maximum >= 0 else None
                )
            else:
                score = number(row.get("weighted_score"))
                score = round(score, 4) if score is not None else None

            row["effective_minwithdraw"] = effective_min
            row["ratio"] = ratio
            row["rollover_ratio_average"] = burden
            row["weighted_score"] = score
            rows.append(row)

    fields = [field for field in source_fields if field not in DROP_COLUMNS]
    for field in ("effective_minwithdraw", "ratio", "rollover_ratio_average", "weighted_score"):
        if field not in fields:
            fields.append(field)

    if "perceived_value" in fields:
        perceived = [number(row.get("perceived_value")) for row in rows]
        scores = [number(row.get("weighted_score")) for row in rows]
        perceived_ranks = _rank_desc_min(perceived)
        score_ranks = _rank_desc_min(scores)
        for row, pv_rank, score_rank in zip(rows, perceived_ranks, score_ranks):
            row["perceived_value_rank"] = pv_rank
            row["weighted_score_rank"] = score_rank
            row["score_rank_change"] = pv_rank - score_rank
        for field in ("perceived_value_rank", "weighted_score_rank", "score_rank_change"):
            if field not in fields:
                fields.append(field)

    # Match the established filter and first-occurrence duplicate policy.
    rows = [row for row in rows if row["ratio"] is None or row["ratio"] <= 500]
    filtered_count = len(rows)
    seen = set()
    deduplicated = []
    for row in rows:
        key = (row.get("url"), row.get("name"), row.get("amount"))
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(row)

    # Stable sorting keeps source order for equal scores and puts missing
    # scores last, matching the previous DataFrame behavior.
    if "weighted_score" in fields:
        deduplicated.sort(
            key=lambda row: (
                number(row.get("weighted_score")) is None,
                -(number(row.get("weighted_score")) or 0.0),
            )
        )
    elif "perceived_value" in fields:
        deduplicated.sort(
            key=lambda row: (
                number(row.get("perceived_value")) is None,
                -(number(row.get("perceived_value")) or 0.0),
            )
        )

    derived = ["effective_minwithdraw", "ratio", "rollover_ratio_average", "weighted_score"]
    fields = [field for field in fields if field not in derived]
    if "rollover" in fields:
        index = fields.index("rollover") + 1
        fields[index:index] = derived
    else:
        fields.extend(derived)

    print(
        f"Filtered: {filtered_count} -> {len(deduplicated)} rows "
        f"({filtered_count - len(deduplicated)} duplicates removed)"
    )
    return fields, deduplicated


def write_cleaned_csv(fieldnames, rows, output_path):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    source = sys.argv[1] if len(sys.argv) > 1 else "data/Dayne_Bonuses.csv"
    fields, cleaned = clean_bonuses(source)
    destination = Path("data/Dayne_Bonuses_Cleaned.csv")
    write_cleaned_csv(fields, cleaned, destination)
    print(f"Saved: {destination} ({len(cleaned)} rows)")
