#!/usr/bin/env python3
"""Canonical CSV export helpers shared by CLI, build_exports and viewers."""
from __future__ import annotations

import csv
import json
import math
import sqlite3
from statistics import median
from bonus_scoring import score_bonus
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_DB = Path("data/base.db")
DEFAULT_OUT = Path("data")

BONUS_SELECT = (
    "SELECT bonus_uid, external_id, url, amount, perceived_value, wager, claim, kind, "
    "raw_json, content_hash, expiry, fingerprint, mirrors, first_seen, last_seen, "
    "merchant_name, name FROM bonuses ORDER BY url, name"
)

ENRICHED_HEADERS = [
    "url", "mname", "eid", "name", "transactiontype", "bonusfixed", "amount", "minwithdraw",
    "site_minwithdraw", "effective_minwithdraw", "maxwithdraw", "rollover", "ratio",
    "rollover_ratio_average", "weighted_score_v1", "weighted_score", "perceived_value",
    "score_confidence", "score_status", "score_maxwithdraw_source", "score_rollover_source",
    "score_maxwithdraw_used", "score_rollover_used", "is_new", "expiry",
    "first_seen", "last_seen", "referlink", "claimconfig", "claimcondition", "bonus",
    "bonusrandom", "reset", "mintopup", "maxtopup",
]

DAYNE_HEADERS = [
    "url", "mname", "id", "name", "transactiontype", "bonusfixed", "amount", "minwithdraw",
    "maxwithdraw", "rollover", "balance", "claimconfig", "claimcondition", "bonus",
    "bonusrandom", "reset", "mintopup", "maxtopup", "referlink", "perceived_value", "is_new",
]


def num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def domain(url):
    host = (urlparse(str(url)).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def site_minimums(out_dir: Path | None = None):
    out_dir = out_dir or DEFAULT_OUT
    path = out_dir / "site_min_withdrawals.csv"
    result = {}
    if not path.exists():
        return result
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            value = num(row.get("site_minwithdraw"))
            if row.get("domain") and value and value > 0:
                result[row["domain"].strip().lower()] = value
    return result


def normalize_bonus_json(raw_json):
    """Decode a raw bonus payload and normalize keys without trusting its shape."""
    try:
        value = json.loads(raw_json or "{}")
    except (TypeError, ValueError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {str(key).lower(): item for key, item in value.items()}


def build_scoring_context(rows):
    """Calculate the shared per-site and dataset medians used by every exporter."""
    site_maxes, site_rolls, all_maxes, all_rolls = {}, {}, [], []
    for row in rows:
        raw = normalize_bonus_json(row["raw_json"])
        host = domain(row["url"])
        maximum, rollover = num(raw.get("maxwithdraw")), num(raw.get("rollover"))
        if maximum is not None and maximum > 0:
            all_maxes.append(maximum)
            site_maxes.setdefault(host, []).append(maximum)
        if rollover is not None and rollover >= 0:
            all_rolls.append(rollover)
            site_rolls.setdefault(host, []).append(rollover)
    return {
        "site_maxwithdraw": {host: median(values) for host, values in site_maxes.items()},
        "site_rollover": {host: median(values) for host, values in site_rolls.items()},
        "global_maxwithdraw": median(all_maxes) if all_maxes else None,
        "global_rollover": median(all_rolls) if all_rolls else None,
    }


def score_bonus_row(row, normalized=None, mins=None, context=None):
    """Score one DB row using the same medians and fallback rules in all exports."""
    normalized = normalized if normalized is not None else normalize_bonus_json(row["raw_json"])
    mins = mins or {}
    context = context or {}
    host = domain(row["url"])
    amount = num(normalized.get("amount", row["amount"]))
    return score_bonus(
        amount, normalized.get("minwithdraw"), mins.get(host),
        num(normalized.get("maxwithdraw")), num(normalized.get("rollover")),
        context.get("site_maxwithdraw", {}).get(host),
        context.get("site_rollover", {}).get(host),
        context.get("global_maxwithdraw"), context.get("global_rollover"),
    )


def connect(db_path: Path | str | None = None):
    if db_path is None:
        try:
            import db as _db
            path = Path(_db.DB_PATH)
        except Exception:
            path = DEFAULT_DB
    else:
        path = Path(db_path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def fetch_bonus_rows(db_path: Path | str | None = None):
    conn = connect(db_path)
    try:
        return conn.execute(BONUS_SELECT).fetchall()
    finally:
        conn.close()


def write_raw(rows, out_dir: Path | None = None):
    out_dir = out_dir or DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    extra_keys = set()
    for row in rows:
        try:
            raw = json.loads(row["raw_json"] or "{}")
        except Exception:
            raw = {}
        normalized = {str(k).lower(): v for k, v in raw.items()}
        extra_keys.update(normalized.keys())
        records.append((row, raw, normalized))

    fixed = [
        "uid", "eid", "url", "merchant", "name", "amount_db", "perceived_value_db",
        "w", "c", "t", "raw_json", "hash", "expiry", "fingerprint", "mirrors",
        "first_seen", "last_seen",
    ]
    fields = fixed + sorted(k for k in extra_keys if k not in fixed)
    with (out_dir / "Dayne_Bonuses_Raw.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row, raw, normalized in records:
            payload = {
                "uid": row["bonus_uid"], "eid": row["external_id"], "url": row["url"],
                "merchant": row["merchant_name"] or "", "name": row["name"] or "",
                "amount_db": row["amount"] or "", "perceived_value_db": row["perceived_value"] or "",
                "w": row["wager"] or "", "c": row["claim"] or "", "t": row["kind"] or "",
                "raw_json": row["raw_json"] or "", "hash": row["content_hash"] or "",
                "expiry": row["expiry"] or "", "fingerprint": row["fingerprint"] or "",
                "mirrors": row["mirrors"] or "", "first_seen": row["first_seen"] or "",
                "last_seen": row["last_seen"] or "",
            }
            payload.update(normalized)
            writer.writerow(payload)


def write_enriched(rows, mins=None, out_dir: Path | None = None):
    out_dir = out_dir or DEFAULT_OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    mins = mins if mins is not None else site_minimums(out_dir)
    prepared = []
    scoring_context = build_scoring_context(rows)
    for row in rows:
        normalized = normalize_bonus_json(row["raw_json"])
        amount = num(normalized.get("amount", row["amount"]))
        host = domain(row["url"])
        prepared.append((row, normalized, amount, host))
    with (out_dir / "Dayne_Bonuses.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ENRICHED_HEADERS)
        writer.writeheader()
        for row, normalized, amount, host in prepared:
            site_min = mins.get(host)
            score = score_bonus_row(row, normalized, mins, scoring_context)
            effective = score["effective_minwithdraw"]
            ratio = round(effective / amount, 4) if effective and amount and amount > 0 else None
            writer.writerow({
                "url": row["url"], "mname": row["merchant_name"] or "", "eid": row["external_id"] or "",
                "name": row["name"] or normalized.get("name", ""),
                "transactiontype": normalized.get("transactiontype", ""), "bonusfixed": normalized.get("bonusfixed", ""),
                "amount": normalized.get("amount", row["amount"]), "minwithdraw": normalized.get("minwithdraw", ""),
                "site_minwithdraw": site_min or "", "effective_minwithdraw": effective if effective is not None else "",
                "maxwithdraw": normalized.get("maxwithdraw", ""), "rollover": normalized.get("rollover", ""),
                "ratio": ratio if ratio is not None else "",
                "rollover_ratio_average": score["rollover_ratio_average"] if score["rollover_ratio_average"] is not None else "",
                "weighted_score_v1": round(score["weighted_score_v1"], 4) if score["weighted_score_v1"] is not None else "",
                "weighted_score": round(score["weighted_score"], 4) if score["weighted_score"] is not None else "",
                "perceived_value": row["perceived_value"] if row["perceived_value"] is not None else "",
                "score_confidence": score["score_confidence"], "score_status": score["score_status"],
                "score_maxwithdraw_source": score["score_maxwithdraw_source"],
                "score_rollover_source": score["score_rollover_source"],
                "score_maxwithdraw_used": score["score_maxwithdraw_used"] if score["score_maxwithdraw_used"] is not None else "",
                "score_rollover_used": score["score_rollover_used"] if score["score_rollover_used"] is not None else "",
                "is_new": 0, "expiry": row["expiry"] or "", "first_seen": row["first_seen"] or "",
                "last_seen": row["last_seen"] or "", "referlink": normalized.get("referlink", ""),
                "claimconfig": normalized.get("claimconfig", ""), "claimcondition": normalized.get("claimcondition", ""),
                "bonus": normalized.get("bonus", ""), "bonusrandom": normalized.get("bonusrandom", ""),
                "reset": normalized.get("reset", ""), "mintopup": normalized.get("mintopup", ""),
                "maxtopup": normalized.get("maxtopup", ""),
            })


def write_dayne_simple(rows, out_path: Path | str | None = None):
    """Write the flat Dayne_Bonuses.csv shape used by the fast/legacy exporter."""
    path = Path(out_path) if out_path else DEFAULT_OUT / "Dayne_Bonuses.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DAYNE_HEADERS)
        writer.writeheader()
        for row in rows:
            normalized = normalize_bonus_json(row["raw_json"])
            writer.writerow({
                "url": row["url"],
                "mname": row["merchant_name"] or "",
                "id": row["external_id"] or "",
                "name": row["name"] or "",
                "transactiontype": normalized.get("transactiontype", ""),
                "bonusfixed": normalized.get("bonusfixed", ""),
                "amount": row["amount"] if row["amount"] else normalized.get("amount", ""),
                "minwithdraw": normalized.get("minwithdraw", ""),
                "maxwithdraw": normalized.get("maxwithdraw", ""),
                "rollover": normalized.get("rollover", ""),
                "balance": normalized.get("balance", ""),
                "claimconfig": normalized.get("claimconfig", ""),
                "claimcondition": normalized.get("claimcondition", ""),
                "bonus": normalized.get("bonus", ""),
                "bonusrandom": normalized.get("bonusrandom", ""),
                "reset": normalized.get("reset", ""),
                "mintopup": normalized.get("mintopup", ""),
                "maxtopup": normalized.get("maxtopup", ""),
                "referlink": normalized.get("referlink", ""),
                "perceived_value": row["perceived_value"] if row["perceived_value"] else "",
                "is_new": 1 if row["last_seen"] and row["last_seen"] == row["first_seen"] else 0,
            })
    return len(rows)


def build_analysis_exports(db_path: Path | str | None = None, out_dir: Path | None = None):
    out_dir = out_dir or DEFAULT_OUT
    rows = fetch_bonus_rows(db_path)
    mins = site_minimums(out_dir)
    write_raw(rows, out_dir)
    write_enriched(rows, mins, out_dir)
    return len(rows)


def export_db_to_csv(db_path: Path | str | None = None, out_path: Path | str | None = None):
    rows = fetch_bonus_rows(db_path)
    count = write_dayne_simple(rows, out_path)
    print(f"\nExported {count} bonuses to {out_path or DEFAULT_OUT / 'Dayne_Bonuses.csv'}")
    return count


if __name__ == "__main__":
    DEFAULT_OUT.mkdir(parents=True, exist_ok=True)
    n = build_analysis_exports()
    print(f"Exported {n} DB bonuses to raw + enriched CSVs")
