#!/usr/bin/env python3
"""Extract qualifying bonuses from raw response JSONs.

Filters:
  a) effective amount >= 0.5
  b) minWithdraw / amount <= 30  (ratio ≤ 30x)

Output columns:
  url, amount, minwithdraw, maxwithdraw, rollover,
  ratio (= minWithdraw / amount, 0 if no min),
  mintopup, maxtopup
"""

import csv
import json
import sys
from pathlib import Path

RAW_DIR = Path("data/raw_responses")
OUTPUT = Path("data/extracted_bonuses.csv")

OUTPUT_HEADERS = [
    "url", "amount", "minwithdraw", "maxwithdraw", "rollover",
    "ratio", "mintopup", "maxtopup",
]


def float_val(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def get_amount(n):
    """Try amount → bonusfixed → bonus as the effective amount."""
    for key in ("amount", "bonusfixed", "bonus"):
        v = n.get(key)
        if v is not None:
            fv = float_val(v)
            if fv > 0:
                return fv
    return 0.0


def main():
    files = sorted(RAW_DIR.glob("*.json"))
    if not files:
        print(f"No JSON files found in {RAW_DIR}", file=sys.stderr)
        sys.exit(1)

    def site_url_from_name(fname):
        parts = fname.stem.split("_", 2)
        return f"https://{parts[2]}" if len(parts) >= 3 else fname.stem

    rows = []
    for fp in files:
        try:
            data = json.loads(fp.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"SKIP {fp.name}: {e}", file=sys.stderr)
            continue

        bonuses = (data.get("data") or {}).get("bonus", []) + \
                  (data.get("data") or {}).get("promotions", [])

        url = site_url_from_name(fp)

        for b in bonuses:
            if not isinstance(b, dict):
                continue

            n = {k.lower(): v for k, v in b.items()}

            # --- Filter a) amount >= 0.5 ---
            amount = get_amount(n)
            if amount < 0.5:
                continue

            # --- Filter b) ratio ≤ 30 ---
            minw = float_val(n.get("minwithdraw"))
            ratio = (minw / amount) if minw > 0 else 0.0
            if minw > 0 and ratio > 30:
                continue

            # --- Build output row ---
            row = {}
            row["url"] = url
            row["amount"] = amount
            row["minwithdraw"] = minw
            row["maxwithdraw"] = float_val(n.get("maxwithdraw"))
            row["rollover"] = float_val(n.get("rollover"))
            row["ratio"] = round(ratio, 2)
            row["mintopup"] = n.get("mintopup", "")
            row["maxtopup"] = n.get("maxtopup", "")
            rows.append(row)

    if not rows:
        print("No qualifying bonuses found.", file=sys.stderr)
        sys.exit(0)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_HEADERS)
        w.writeheader()
        w.writerows(rows)

    print(f"Wrote {len(rows)} qualifying bonuses to {OUTPUT}")


if __name__ == "__main__":
    main()
