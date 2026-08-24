#!/usr/bin/env python3
"""Export the scraper DB into the dayne-bonuses viewer's 5 CSVs.

Matches the schemas the viewer (dayne-bonuses/main.js) consumes:
  dayne-bonuses.csv          - 21-col raw export (same as scrape_and_deploy.sh)
  dayne-bonuses-cleaned.csv  - raw + ratio, amount>0, deduped, pv-sorted
  dayne-bonuses-fresh.csv    - copy of raw (historical behavior)
  dayne-bonuses-all.csv      - 49-col all-time export (raw JSON + db fields)
  dayne-sites.csv            - 40-col per-site rollup

Usage: python3 export_viewer_data.py [output_dir]
"""
import csv
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path("data/base.db")
OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("viewer/public")

RAW_HEADERS = ["url", "mname", "id", "name", "transactiontype", "bonusfixed",
               "amount", "minwithdraw", "maxwithdraw", "rollover", "balance",
               "claimconfig", "claimcondition", "bonus", "bonusrandom", "reset",
               "mintopup", "maxtopup", "referlink", "perceived_value", "is_new"]

ALL_HEADERS = ["url", "mname", "id", "name", "amount", "perceived_value",
               "expiry", "first_seen", "last_seen", "angpaoid", "angpaoimage",
               "bonus", "bonusfixed", "bonusrandom", "claimcondition",
               "claimconfig", "claimdatetime", "createddatetime",
               "depositfreelimit", "description", "displayamount",
               "displaygroup", "displayorder", "image", "initialfreelimit",
               "maxround", "maxtopup", "maxwithdraw", "message", "minbet",
               "minbetignorebalance", "minround", "mintopup", "minwithdraw",
               "reset", "rollover", "sysnote", "transactioncash",
               "transactionid", "transactiontype", "updata", "ratio",
               "headroom", "rollover_amount", "value_per_rollover",
               "days_visible", "bonus_lifetime_days", "is_commission",
               "is_surprise"]

SITES_HEADERS = ["url", "mname", "source", "status", "failures",
                 "last_checked", "first_seen", "last_seen", "tracked_days",
                 "bonus_count", "window_count", "last_24h_count",
                 "prev_24h_count", "distinct_days", "total_amount",
                 "avg_amount", "max_amount", "total_perceived",
                 "avg_perceived", "commission_count", "commission_total",
                 "avg_minwithdraw", "avg_maxwithdraw", "avg_rollover",
                 "bonuses_per_day", "recent_share", "growth_24h",
                 "hours_since_seen", "avg_withdraw_headroom", "avg_ratio",
                 "avg_rollover_burden", "value_per_bonus",
                 "value_per_rollover", "commission_share",
                 "avg_bonus_lifetime_days", "stability", "avg_daily_value",
                 "active_today", "referral_url", "short_url"]

STATUS_BY_EC = {200: "OK", 301: "Redirect", 403: "Blocked", 404: "Not Found",
                405: "Method Not Allowed", 408: "Timeout", 503: "Error",
                530: "Code 530"}


def fnum(v, nd=1):
    """Format float to nd decimals, or '' for non-finite."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    if v != v or v in (float("inf"), float("-inf")):
        return ""
    return f"{v:.{nd}f}"


def num(v):
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def fmt_dt(v):
    return v if v else ""


def days_between(a, b):
    try:
        da = datetime.strptime(a, "%Y-%m-%d %H:%M:%S")
        db = datetime.strptime(b, "%Y-%m-%d %H:%M:%S")
        return (db - da).total_seconds() / 86400.0
    except (TypeError, ValueError):
        return None


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    bonus_rows = [dict(r) for r in c.execute(
        "SELECT uid, eid, u, v, pv, raw, exp, s1, sl, mname, name FROM b")]
    site_rows = [dict(r) for r in c.execute(
        "SELECT u, m, p, g, ts, ec FROM t")]

    now = datetime.now()
    raw_rows = []
    all_rows = []
    by_url = {}
    for b in bonus_rows:
        raw_json = b["raw"]
        try:
            bonus = json.loads(raw_json) if raw_json else {}
            bonus = {k.lower(): val for k, val in bonus.items()} if isinstance(bonus, dict) else {}
        except (ValueError, TypeError):
            bonus = {}
        amount = b["v"] if b["v"] is not None else bonus.get("amount", "")
        pv = b["pv"]
        exp, s1, sl = b["exp"], b["s1"], b["sl"]
        is_new = 1 if sl and s1 and sl == s1 else 0

        # ── raw / fresh row (same export logic as scrape_and_deploy.sh) ──
        raw_rows.append({
            "url": b["u"] or "", "mname": b["mname"] or "", "id": b["eid"] or "",
            "name": b["name"] or "", "transactiontype": bonus.get("transactiontype", ""),
            "bonusfixed": bonus.get("bonusfixed", ""), "amount": amount,
            "minwithdraw": bonus.get("minwithdraw", ""),
            "maxwithdraw": bonus.get("maxwithdraw", ""),
            "rollover": bonus.get("rollover", ""), "balance": bonus.get("balance", ""),
            "claimconfig": bonus.get("claimconfig", ""),
            "claimcondition": bonus.get("claimcondition", ""),
            "bonus": bonus.get("bonus", ""), "bonusrandom": bonus.get("bonusrandom", ""),
            "reset": bonus.get("reset", ""), "mintopup": bonus.get("mintopup", ""),
            "maxtopup": bonus.get("maxtopup", ""), "referlink": bonus.get("referlink", ""),
            "perceived_value": pv if pv is not None else "", "is_new": is_new,
        })

        # ── all row (49-col all-time export) ──
        amt = num(amount)
        minw = num(bonus.get("minwithdraw"))
        maxw = num(bonus.get("maxwithdraw"))
        roll = num(bonus.get("rollover"))
        ratio = round(minw / amt, 3) if amt and minw and amt > 0 else ""
        headroom = round(maxw - minw, 1) if minw is not None and maxw is not None else ""
        roll_amt = round(amt * roll, 1) if amt is not None and roll is not None else ""
        pvn = num(pv)
        vpr = (round(pvn / roll, 3) if pvn is not None and roll and roll > 0
               else (round(pvn, 3) if pvn is not None else ""))
        days_vis = ""
        if s1 and sl:
            d = days_between(s1, sl)
            if d is not None:
                days_vis = round(d, 2)
        name_l = (b["name"] or "").lower()
        all_rows.append({
            "url": b["u"] or "", "mname": b["mname"] or "", "id": b["eid"] or "",
            "name": b["name"] or "", "amount": amount,
            "perceived_value": pv if pv is not None else "",
            "expiry": fmt_dt(exp), "first_seen": fmt_dt(s1), "last_seen": fmt_dt(sl),
            "angpaoid": bonus.get("angpaoid", ""), "angpaoimage": bonus.get("angpaoimage", ""),
            "bonus": bonus.get("bonus", ""), "bonusfixed": bonus.get("bonusfixed", ""),
            "bonusrandom": bonus.get("bonusrandom", ""),
            "claimcondition": bonus.get("claimcondition", ""),
            "claimconfig": bonus.get("claimconfig", ""),
            "claimdatetime": bonus.get("claimdatetime", ""),
            "createddatetime": bonus.get("createddatetime", ""),
            "depositfreelimit": bonus.get("depositfreelimit", ""),
            "description": bonus.get("description", ""),
            "displayamount": bonus.get("displayamount", ""),
            "displaygroup": bonus.get("displaygroup", ""),
            "displayorder": bonus.get("displayorder", ""),
            "image": bonus.get("image", ""),
            "initialfreelimit": bonus.get("initialfreelimit", ""),
            "maxround": bonus.get("maxround", ""), "maxtopup": bonus.get("maxtopup", ""),
            "maxwithdraw": bonus.get("maxwithdraw", ""), "message": bonus.get("message", ""),
            "minbet": bonus.get("minbet", ""),
            "minbetignorebalance": bonus.get("minbetignorebalance", ""),
            "minround": bonus.get("minround", ""), "mintopup": bonus.get("mintopup", ""),
            "minwithdraw": bonus.get("minwithdraw", ""), "reset": bonus.get("reset", ""),
            "rollover": bonus.get("rollover", ""), "sysnote": bonus.get("sysnote", ""),
            "transactioncash": bonus.get("transactioncash", ""),
            "transactionid": bonus.get("transactionid", ""),
            "transactiontype": bonus.get("transactiontype", ""),
            "updata": bonus.get("updata", ""), "ratio": ratio, "headroom": headroom,
            "rollover_amount": roll_amt, "value_per_rollover": vpr,
            "days_visible": days_vis, "bonus_lifetime_days": days_vis,
            "is_commission": 1 if ("commission" in name_l or "downline" in name_l) else 0,
            "is_surprise": 1 if ("surprise" in name_l or "red envelope" in name_l
                                 or "angpao" in name_l) else 0,
        })

        by_url.setdefault(b["u"], []).append({
            "v": b["v"], "pv": pv, "s1": s1, "sl": sl, "raw": bonus,
            "name": b["name"] or "",
        })

    # ── cleaned row: raw + ratio, amount>0, deduped, pv-sorted ──
    cleaned_rows = []
    seen = set()
    for r in raw_rows:
        amt = num(r["amount"])
        if amt is None or amt <= 0:
            continue
        key = (r["url"], r["name"], str(r["amount"]))
        if key in seen:
            continue
        seen.add(key)
        row = dict(r)
        minw = num(r["minwithdraw"])
        row["ratio"] = round(minw / amt, 2) if minw and minw > 0 else 0.0
        cleaned_rows.append(row)
    cleaned_rows.sort(key=lambda r: num(r["perceived_value"]) or 0.0, reverse=True)
    for r in cleaned_rows:
        del r["ratio"]  # re-insert after rollover below
    cleaned_final = []
    for r in cleaned_rows:
        out = {}
        for h in RAW_HEADERS:
            out[h] = r[h]
            if h == "rollover":
                out["ratio"] = r.get("ratio", 0.0)
        cleaned_final.append(out)

    # ── sites rollup ──
    sites_rows = []
    for s in site_rows:
        u = s["u"] or ""
        bs = by_url.get(u, [])
        bc = len(bs)
        last_checked = s["ts"] or ""
        first_seen = min((b["s1"] for b in bs if b["s1"]), default="")
        last_seen = max((b["sl"] for b in bs if b["sl"]), default="")
        span_ref = last_seen or last_checked
        tracked = None
        if first_seen and span_ref:
            d = days_between(first_seen, span_ref)
            if d is not None:
                tracked = max(d, 0.0)

        amounts = [num(b["v"]) for b in bs]
        amounts = [a for a in amounts if a is not None]
        pvs = [num(b["pv"]) for b in bs]
        pvs = [p for p in pvs if p is not None]

        minws, maxws, rolls = [], [], []
        for b in bs:
            rw = b["raw"]
            minws.append(num(rw.get("minwithdraw")))
            maxws.append(num(rw.get("maxwithdraw")))
            rolls.append(num(rw.get("rollover")))
        minws = [x for x in minws if x is not None]
        maxws = [x for x in maxws if x is not None]
        rolls = [x for x in rolls if x is not None]

        ratios = []
        burdens = []
        for b in bs:
            a = num(b["v"])
            rw = b["raw"]
            if a is None or a <= 0:
                continue
            mw = num(rw.get("minwithdraw"))
            rl = num(rw.get("rollover"))
            if mw is not None and mw > 0:
                ratios.append(mw / a)
            if mw is not None or rl is not None:
                burdens.append(max(mw or 0.0, (a * (rl or 0.0))) / a)

        sl_list = sorted(b["sl"] for b in bs if b["sl"])
        distinct_days = len({s[:10] for s in sl_list})
        day24 = now - timedelta(hours=24)
        day48 = now - timedelta(hours=48)
        last24 = sum(1 for s in sl_list if datetime.strptime(s, "%Y-%m-%d %H:%M:%S") >= day24)
        prev24 = sum(1 for s in sl_list if day48 <= datetime.strptime(s, "%Y-%m-%d %H:%M:%S") < day24)

        total_amt = sum(amounts)
        total_pv = sum(pvs)
        lifetime = []
        for b in bs:
            if b["s1"] and b["sl"]:
                d = days_between(b["s1"], b["sl"])
                if d is not None:
                    lifetime.append(d)

        ec = s["ec"]
        status = STATUS_BY_EC.get(ec, "Error" if ec not in (None,) else "")

        def avg(xs, nd=1):
            return fnum(sum(xs) / len(xs), nd) if xs else ""

        vpr_vals = []
        for b in bs:
            pvn = num(b["pv"])
            rw = b["raw"]
            rl = num(rw.get("rollover"))
            if pvn is None:
                continue
            vpr_vals.append(pvn / rl if rl and rl > 0 else pvn)

        sites_rows.append({
            "url": u, "mname": s["m"] or "", "source": "urls",
            "status": status, "failures": 0, "last_checked": fmt_dt(last_checked),
            "first_seen": fmt_dt(first_seen), "last_seen": fmt_dt(last_seen),
            "tracked_days": fnum(tracked, 1) if tracked is not None else "",
            "bonus_count": bc, "window_count": len({b["raw"].get("reset") for b in bs if b["raw"].get("reset")}) if bs else 0,
            "last_24h_count": last24, "prev_24h_count": prev24,
            "distinct_days": distinct_days,
            "total_amount": fnum(total_amt, 1), "avg_amount": avg(amounts),
            "max_amount": fnum(max(amounts), 1) if amounts else "",
            "total_perceived": fnum(total_pv, 2), "avg_perceived": avg(pvs, 2),
            "commission_count": 0, "commission_total": "0.0",
            "avg_minwithdraw": avg(minws), "avg_maxwithdraw": avg(maxws),
            "avg_rollover": avg(rolls),
            "bonuses_per_day": fnum(bc / tracked, 3) if tracked and tracked > 0 else "",
            "recent_share": fnum(last24 / bc, 1) if bc else "",
            "growth_24h": last24 - prev24,
            "hours_since_seen": fnum((now - datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600.0, 1) if last_seen else "",
            "avg_withdraw_headroom": avg([abs(a - b) for a, b in zip(maxws, minws)]) if minws and maxws else "",
            "avg_ratio": avg(ratios, 3),
            "avg_rollover_burden": avg(burdens),
            "value_per_bonus": avg(pvs, 2),
            "value_per_rollover": avg(vpr_vals, 2),
            "commission_share": "0.0",
            "avg_bonus_lifetime_days": avg(lifetime, 2),
            "stability": fnum(distinct_days / tracked, 3) if tracked and tracked > 0 else "",
            "avg_daily_value": fnum(total_pv / tracked, 2) if tracked and tracked > 0 else "",
            "active_today": 1 if last24 else 0,
            "referral_url": s["p"] or "", "short_url": s["g"] or "",
        })

    def write_csv(name, headers, rows):
        out = OUT_DIR / name
        with out.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print(f"{name}: {len(rows)} rows -> {out}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv("dayne-bonuses.csv", RAW_HEADERS, raw_rows)
    write_csv("dayne-bonuses-fresh.csv", RAW_HEADERS, raw_rows)
    cleaned_headers = RAW_HEADERS[:10] + ["ratio"] + RAW_HEADERS[10:]
    write_csv("dayne-bonuses-cleaned.csv", cleaned_headers, cleaned_final)
    write_csv("dayne-bonuses-all.csv", ALL_HEADERS, all_rows)
    write_csv("dayne-sites.csv", SITES_HEADERS, sites_rows)
    print(f"Snapshot time: {now.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
