#!/usr/bin/env python3
"""Track daily bonus changes and infer commission release weekdays."""
import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

HISTORY_PATH = Path("viewer/public/bonus-history.json")
RETENTION_DAYS = 365
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
COMPARE_FIELDS = ["name", "amount", "minwithdraw", "maxwithdraw", "rollover", "reset",
                  "claimcondition", "transactiontype", "mintopup", "maxtopup"]


def clean(value):
    return re.sub(r"\\s+", " ", str(value or "")).strip()


def number(value):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def is_commission(bonus):
    text = " ".join(clean(bonus.get(k)).lower() for k in ("name", "transactiontype", "claimcondition"))
    return bool(re.search(r"commission|downline|agent rebate|agent income", text))


def bonus_key(url, bonus):
    external_id = clean(bonus.get("id"))
    identity = "id:" + external_id if external_id else "name:" + clean(bonus.get("name")).casefold()
    if identity == "name:":
        identity += hashlib.sha256(json.dumps(bonus, sort_keys=True).encode()).hexdigest()[:16]
    return hashlib.sha256((url + "|" + identity).encode()).hexdigest()[:24]


def signature(bonus):
    stable = {field: bonus.get(field) for field in COMPARE_FIELDS}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def load_csv(path):
    grouped = defaultdict(list)
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            url = clean(row.get("url"))
            if not url:
                continue
            bonus = {field: clean(row.get(field)) for field in COMPARE_FIELDS}
            for field in ("amount", "minwithdraw", "maxwithdraw", "rollover", "mintopup", "maxtopup"):
                bonus[field] = number(row.get(field))
            bonus["id"] = clean(row.get("id"))
            bonus["name"] = clean(row.get("name"))
            bonus["perceived_value"] = number(row.get("perceived_value"))
            bonus["is_commission"] = is_commission(bonus)
            bonus["key"] = bonus_key(url, bonus)
            bonus["signature"] = signature(bonus)
            grouped[url].append(bonus)
    return grouped


def load_history():
    try:
        value = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        if isinstance(value, dict) and isinstance(value.get("site_baseline"), dict):
            value.setdefault("runs", [])
            value.setdefault("events", [])
            return value
    except (OSError, ValueError):
        pass
    return {"version": 1, "site_baseline": {}, "runs": [], "events": []}


def compact_bonus(bonus):
    return {key: bonus.get(key) for key in (
        "key", "signature", "id", "name", "amount", "minwithdraw", "maxwithdraw",
        "rollover", "reset", "claimcondition", "transactiontype", "mintopup",
        "maxtopup", "perceived_value", "is_commission"
    )}


def make_event(kind, url, merchant, bonus, previous=None):
    event = {"type": kind, "date": None, "url": url, "merchant": merchant or url,
             "key": bonus["key"], "bonus": compact_bonus(bonus)}
    if previous is not None:
        event["previous"] = compact_bonus(previous)
    return event


def build_analytics(events, runs, generated_at, site_baseline):
    commission_events = [event for event in events if event["type"] == "new_commission"]
    overall = Counter()
    by_site = defaultdict(Counter)
    site_release_history = defaultdict(list)
    names = {url: item.get("merchant") or url for url, item in site_baseline.items()}
    for event in commission_events:
        weekday = date.fromisoformat(event["date"]).weekday()
        overall[weekday] += 1
        by_site[event["url"]][weekday] += 1
        site_release_history[event["url"]].append({
            "date": event["date"], "weekday": WEEKDAYS[weekday],
            "name": event["bonus"].get("name", ""), "amount": event["bonus"].get("amount"),
            "key": event["key"], "url": event["url"], "merchant": event.get("merchant", event["url"])
        })
    total = sum(overall.values())
    weekday_rows = [{"weekday": WEEKDAYS[i], "count": overall[i],
                     "share": round(overall[i] / total, 4) if total else 0}
                    for i in range(7)]
    site_rows = []
    for url in sorted(set(names) | set(by_site)):
        counts = by_site[url]
        release_total = sum(counts.values())
        ranked = [{"weekday": WEEKDAYS[i], "count": counts[i],
                   "share": round(counts[i] / release_total, 4) if release_total else 0}
                  for i in range(7)]
        ranked.sort(key=lambda row: (-row["count"], WEEKDAYS.index(row["weekday"])))
        history = sorted(site_release_history[url], key=lambda row: row["date"])
        site_rows.append({
            "url": url, "merchant": names.get(url, url),
            "observed_days": site_baseline.get(url, {}).get("observed_days", 0),
            "commission_release_count": release_total,
            "likely_weekday": ranked[0]["weekday"] if release_total and ranked[0]["count"] else None,
            "weekday_counts": ranked,
            "last_commission_release": history[-1]["date"] if history else None,
            "commission_releases": history[-30:],
            "confidence": "low" if release_total < 3 else "moderate" if release_total < 8 else "higher"
        })
    site_rows.sort(key=lambda row: (-row["commission_release_count"], row["merchant"].casefold()))
    recent = sorted(commission_events, key=lambda row: (row["date"], row.get("merchant", "")), reverse=True)
    return {
        "generated_at": generated_at, "history_days": RETENTION_DAYS,
        "weekday_releases": weekday_rows, "sites": site_rows,
        "recent_commission_releases": recent[:300], "release_count": total,
        "methodology": {
            "release_definition": "A commission bonus first observed after a prior successful scrape of the same site did not contain it.",
            "weekday_basis": "The local calendar day on which the daily scraper first observed the bonus.",
            "caveat": "This estimates release patterns, not exact publication time. Bonuses present at the first successful baseline are not counted as new releases."
        }
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="CSV produced by this scraper run")
    parser.add_argument("--started-at", required=True, help="Run start time: YYYY-MM-DD HH:MM:SS")
    parser.add_argument("--date", default=None, help="Snapshot date YYYY-MM-DD")
    args = parser.parse_args()

    started = datetime.strptime(args.started_at, "%Y-%m-%d %H:%M:%S")
    snapshot_date = args.date or date.today().isoformat()
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    import db
    db.initialize_database()
    rows = db.execute("SELECT u, m, ts, ec FROM t WHERE ts >= ?", (args.started_at,))
    attempts = {}
    for url, merchant, checked_at, error_code in rows:
        attempts[url] = {"status": "success" if error_code == 200 else "failed",
                         "merchant": merchant or "", "checked_at": checked_at or "",
                         "error_code": error_code}
    grouped = load_csv(args.csv)
    history = load_history()
    baseline = history["site_baseline"]
    current_events = []
    successful = 0
    for url, state in attempts.items():
        if state["status"] != "success":
            continue
        successful += 1
        bonuses = grouped.get(url, [])
        old_site = baseline.get(url)
        old_bonuses = {bonus["key"]: bonus for bonus in old_site.get("bonuses", [])} if old_site else {}
        new_bonuses = {bonus["key"]: bonus for bonus in bonuses}
        if old_site is not None:
            for key, bonus in new_bonuses.items():
                old = old_bonuses.get(key)
                if old is None:
                    kind = "new_commission" if bonus.get("is_commission") else "new_bonus"
                    current_events.append(make_event(kind, url, state["merchant"], bonus))
                elif old.get("signature") != bonus.get("signature"):
                    current_events.append(make_event("changed_bonus", url, state["merchant"], bonus, old))
            for key, old in old_bonuses.items():
                if key not in new_bonuses:
                    current_events.append(make_event("disappeared_bonus", url, state["merchant"], old))
        baseline[url] = {
            "merchant": state["merchant"] or (old_site or {}).get("merchant") or url,
            "last_success_date": snapshot_date,
            "last_success_at": state["checked_at"],
            "observed_days": int((old_site or {}).get("observed_days", 0)) + 1,
            "bonuses": [compact_bonus(bonus) for bonus in bonuses]
        }

    for event in current_events:
        event["date"] = snapshot_date
        event["observed_at"] = generated_at

    # Re-running the workflow on the same date is idempotent: retain events already
    # observed for that date and merge by site/type/bonus key.
    kept_events = [event for event in history["events"] if event.get("date") != snapshot_date]
    same_day = [event for event in history["events"] if event.get("date") == snapshot_date]
    merged = {(e["type"], e["url"], e["key"]): e for e in same_day}
    merged.update({(e["type"], e["url"], e["key"]): e for e in current_events})
    events = kept_events + list(merged.values())
    cutoff = (date.fromisoformat(snapshot_date).toordinal() - RETENTION_DAYS + 1)
    events = [event for event in events if date.fromisoformat(event["date"]).toordinal() >= cutoff]
    run_summary = {
        "date": snapshot_date, "started_at": started.isoformat(),
        "generated_at": generated_at, "attempted_sites": len(attempts),
        "successful_sites": successful, "failed_sites": len(attempts) - successful,
        "new_commissions": sum(e["type"] == "new_commission" for e in current_events),
        "new_bonuses": sum(e["type"] == "new_bonus" for e in current_events),
        "changed_bonuses": sum(e["type"] == "changed_bonus" for e in current_events),
        "disappeared_bonuses": sum(e["type"] == "disappeared_bonus" for e in current_events)
    }
    runs = [run for run in history["runs"] if run.get("date") != snapshot_date]
    runs.append(run_summary)
    runs.sort(key=lambda run: run["date"])
    runs = runs[-RETENTION_DAYS:]
    analytics = build_analytics(events, runs, generated_at, baseline)
    payload = {"version": 1, "generated_at": generated_at, "runs": runs,
               "events": events, "site_baseline": baseline, "analytics": analytics}
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = HISTORY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    tmp.replace(HISTORY_PATH)
    print(f"History updated: {successful} successful sites, {len(attempts) - successful} failed, "
          f"{run_summary['new_commissions']} new commissions observed")
    print(f"Written: {HISTORY_PATH}")


if __name__ == "__main__":
    main()
