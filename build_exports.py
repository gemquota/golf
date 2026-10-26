#!/usr/bin/env python3
"""Build raw, enriched and analysis-friendly CSV exports from the scraper DB."""
import csv
import json
import math
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

DB = Path("data/base.db")
OUT = Path("data")


def num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def domain(url):
    host = (urlparse(str(url)).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def site_minimums():
    p = OUT / "site_min_withdrawals.csv"
    result = {}
    if not p.exists():
        return result
    with p.open(newline="") as f:
        for row in csv.DictReader(f):
            value = num(row.get("site_minwithdraw"))
            if row.get("domain") and value and value > 0:
                result[row["domain"].strip().lower()] = value
    return result


def fetch_rows():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT uid,eid,u,v,pv,w,c,t,raw,h,exp,fp,mirrors,s1,sl,mname,name FROM b ORDER BY u,name").fetchall()
    finally:
        conn.close()


def write_raw(rows):
    records = []
    extra_keys = set()
    for r in rows:
        try:
            raw = json.loads(r["raw"] or "{}")
        except Exception:
            raw = {}
        normalized = {str(k).lower(): v for k, v in raw.items()}
        extra_keys.update(normalized.keys())
        records.append((r, raw, normalized))

    fixed = ["uid","eid","url","merchant","name","amount_db","perceived_value_db","w","c","t","raw_json","hash","expiry","fingerprint","mirrors","first_seen","last_seen"]
    fields = fixed + sorted(k for k in extra_keys if k not in fixed)
    with (OUT / "Dayne_Bonuses_Raw.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r, raw, normalized in records:
            row = {
                "uid": r["uid"], "eid": r["eid"], "url": r["u"], "merchant": r["mname"] or "",
                "name": r["name"] or "", "amount_db": r["v"] or "", "perceived_value_db": r["pv"] or "",
                "w": r["w"] or "", "c": r["c"] or "", "t": r["t"] or "", "raw_json": r["raw"] or "",
                "hash": r["h"] or "", "expiry": r["exp"] or "", "fingerprint": r["fp"] or "",
                "mirrors": r["mirrors"] or "", "first_seen": r["s1"] or "", "last_seen": r["sl"] or "",
            }
            row.update(normalized)
            writer.writerow(row)


def write_enriched(rows, mins):
    from statistics import median
    from bonus_scoring import score_bonus

    fields = [
        "url", "mname", "eid", "name", "transactiontype", "bonusfixed",
        "amount", "minwithdraw", "site_minwithdraw", "effective_minwithdraw",
        "maxwithdraw", "rollover", "ratio", "rollover_ratio_average",
        "weighted_score_v1", "weighted_score", "perceived_value",
        "score_confidence", "score_status", "score_maxwithdraw_source",
        "score_rollover_source", "score_maxwithdraw_used", "score_rollover_used",
        "is_new", "expiry", "first_seen", "last_seen", "referlink",
        "claimconfig", "claimcondition", "bonus", "bonusrandom", "reset",
        "mintopup", "maxtopup",
    ]

    prepared = []
    site_maxes, site_rolls, all_maxes, all_rolls = {}, {}, [], []
    for r in rows:
        try:
            raw = json.loads(r["raw"] or "{}")
        except Exception:
            raw = {}
        x = {str(k).lower(): v for k, v in raw.items()}
        amt = num(x.get("amount", r["v"]))
        maxw, roll = num(x.get("maxwithdraw")), num(x.get("rollover"))
        host = domain(r["u"])
        prepared.append((r, x, amt, maxw, roll, host))
        if maxw is not None and maxw > 0:
            all_maxes.append(maxw)
            site_maxes.setdefault(host, []).append(maxw)
        if roll is not None and roll >= 0:
            all_rolls.append(roll)
            site_rolls.setdefault(host, []).append(roll)

    global_max = median(all_maxes) if all_maxes else None
    global_roll = median(all_rolls) if all_rolls else None
    site_max_medians = {k: median(v) for k, v in site_maxes.items() if v}
    site_roll_medians = {k: median(v) for k, v in site_rolls.items() if v}

    with (OUT / "Dayne_Bonuses.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r, x, amount, maxw, rollover, host in prepared:
            site_min = mins.get(host)
            score = score_bonus(
                amount=amount,
                minwithdraw=x.get("minwithdraw"),
                site_minwithdraw=site_min,
                maxwithdraw=maxw,
                rollover=rollover,
                site_maxwithdraw=site_max_medians.get(host),
                site_rollover=site_roll_medians.get(host),
                global_maxwithdraw=global_max,
                global_rollover=global_roll,
            )
            effective = score["effective_minwithdraw"]
            ratio = round(effective / amount, 4) if amount and amount > 0 else None
            writer.writerow({
                "url": r["u"], "mname": r["mname"] or "", "eid": r["eid"] or "",
                "name": r["name"] or x.get("name", ""),
                "transactiontype": x.get("transactiontype", ""),
                "bonusfixed": x.get("bonusfixed", ""), "amount": x.get("amount", r["v"]),
                "minwithdraw": x.get("minwithdraw", ""), "site_minwithdraw": site_min or "",
                "effective_minwithdraw": effective, "maxwithdraw": x.get("maxwithdraw", ""),
                "rollover": x.get("rollover", ""), "ratio": ratio,
                "rollover_ratio_average": score["rollover_ratio_average"],
                "weighted_score_v1": score["weighted_score_v1"],
                "weighted_score": score["weighted_score"],
                "perceived_value": r["pv"] if r["pv"] is not None else "",
                "score_confidence": score["score_confidence"],
                "score_status": score["score_status"],
                "score_maxwithdraw_source": score["score_maxwithdraw_source"],
                "score_rollover_source": score["score_rollover_source"],
                "score_maxwithdraw_used": score["score_maxwithdraw_used"] or "",
                "score_rollover_used": score["score_rollover_used"] if score["score_rollover_used"] is not None else "",
                "is_new": 0, "expiry": r["exp"] or "", "first_seen": r["s1"] or "",
                "last_seen": r["sl"] or "", "referlink": x.get("referlink", ""),
                "claimconfig": x.get("claimconfig", ""), "claimcondition": x.get("claimcondition", ""),
                "bonus": x.get("bonus", ""), "bonusrandom": x.get("bonusrandom", ""),
                "reset": x.get("reset", ""), "mintopup": x.get("mintopup", ""),
                "maxtopup": x.get("maxtopup", ""),
            })


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    rows = fetch_rows()
    mins = site_minimums()
    write_raw(rows)
    write_enriched(rows, mins)
    print(f"Exported {len(rows)} DB bonuses to raw + enriched CSVs")
