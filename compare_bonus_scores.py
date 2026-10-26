#!/usr/bin/env python3
"""Compare Perceived Value, weighted v1, and weighted v2 rankings."""
import sys
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


def host(url):
    value = (urlparse(str(url or "")).hostname or "").lower()
    return value[4:] if value.startswith("www.") else value


def main(path=None):
    source = Path(path or "data/Dayne_Bonuses_Cleaned.csv")
    if not source.exists():
        raise SystemExit(f"Input not found: {source}. Run the scrape/export pipeline first.")
    df = pd.read_csv(source)
    required = {"name", "amount", "perceived_value", "weighted_score"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"Missing required columns: {', '.join(sorted(missing))}")

    for col in ("amount", "perceived_value", "weighted_score", "weighted_score_v1"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "weighted_score_v1" not in df:
        df["weighted_score_v1"] = float("nan")

    df["domain"] = df["url"].map(host) if "url" in df else ""
    # Offer-level identity ignores mirror domains but retains terms so distinct
    # versions of a promotion do not collapse merely because their names match.
    identity_fields = ["name", "amount", "minwithdraw", "maxwithdraw", "rollover"]
    for col in identity_fields:
        if col not in df:
            df[col] = ""
    df["_offer_key"] = (
        df["name"].fillna("").astype(str).str.lower().str.strip()
        + "|" + df["amount"].fillna("").astype(str)
        + "|" + df["minwithdraw"].fillna("").astype(str)
        + "|" + df["maxwithdraw"].fillna("").astype(str)
        + "|" + df["rollover"].fillna("").astype(str)
    )
    df = df.drop_duplicates("_offer_key", keep="first").copy()

    for score, ascending in [
        ("perceived_value", False), ("weighted_score_v1", False), ("weighted_score", False)
    ]:
        df[f"{score}_rank"] = df[score].rank(
            ascending=ascending, method="min", na_option="bottom"
        )

    valid = df[["perceived_value", "weighted_score_v1", "weighted_score"]].dropna()
    corr = valid.corr(method="spearman") if len(valid) else pd.DataFrame()
    print(f"Source: {source}")
    print(f"Offer-level rows after mirror/term deduplication: {len(df)}")
    print(f"Rows with all three scores: {len(valid)}")
    if not corr.empty:
        print("\nSpearman rank correlation:")
        print(corr.round(3).to_string())

    for n in (25, 50, 100):
        top_sets = {}
        for score in ("perceived_value", "weighted_score_v1", "weighted_score"):
            top_sets[score] = set(
                df.nlargest(n, score, keep="first")["_offer_key"].tolist()
            )
        print(f"\nTop {n} overlap with Perceived Value:")
        for score in ("weighted_score_v1", "weighted_score"):
            print(f"  {score}: {len(top_sets['perceived_value'] & top_sets[score])}/{n}")

    df["v2_minus_perceived_rank"] = df["perceived_value_rank"] - df["weighted_score_rank"]
    output = Path("data/score_comparison.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    df.sort_values("weighted_score_rank").to_csv(output, index=False)
    print(f"Rank comparison written to {output}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
