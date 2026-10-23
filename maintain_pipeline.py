#!/usr/bin/env python3
"""Maintain scraper state, historical snapshots, site lists and account mapping.

This runs after a scrape.  It deliberately keeps credentials out of the public
viewer: data/accounts.csv is a local operational file and is git-ignored.
"""
import csv
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3

DB = Path("data/base.db")
URLS = Path("in/config/urls.txt")
DOWN = Path("in/config/down.txt")
STATE = Path("data/site_state.json")
ACCOUNT_SUCCESS = Path("data/account_success.json")
ACCOUNTS = Path("data/accounts.csv")
HISTORY = Path("data/bonus_history.csv")
RUN_LOG = Path("data/scrape_runs.csv")
THREE_DAYS = dt.timedelta(days=3)


def now():
    return dt.datetime.now(dt.timezone.utc)


def parse_dt(value):
    if not value:
        return None
    try:
        value = str(value).replace("Z", "+00:00")
        parsed = dt.datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def fmt(value):
    parsed = value if isinstance(value, dt.datetime) else parse_dt(value)
    return parsed.isoformat(timespec="seconds") if parsed else ""


def load_lines(path):
    if not path.exists():
        return []
    return [x.strip() for x in path.read_text().splitlines() if x.strip() and not x.lstrip().startswith("#")]


def unique(values):
    return list(dict.fromkeys(values))


def load_json(path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except Exception:
        return default


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def account_phone_map():
    """Read account usernames from config without ever writing passwords."""
    import config
    result = {}
    for section in config.config_parser.sections():
        if section.startswith("U"):
            user = config._env(f"GOLF_{section.upper()}_USER") or config.config_parser[section].get("u", "")
            if user:
                result[section] = str(user)
    return result


def maintain_sites(run_started):
    urls = unique(load_lines(URLS))
    down = load_lines(DOWN)
    state = load_json(STATE, {})
    successes = load_json(ACCOUNT_SUCCESS, {})
    run_started = parse_dt(run_started) or now()

    conn = sqlite3.connect(DB)
    try:
        rows = conn.execute("SELECT u, ec, ts FROM t").fetchall()
    finally:
        conn.close()

    current_success = {}
    for url, ec, ts in rows:
        checked = parse_dt(ts)
        if url and ec == 200 and checked and checked >= run_started - dt.timedelta(minutes=10):
            current_success[url] = checked

    moved = []
    kept = []
    for url in urls:
        item = state.setdefault(url, {})
        item.setdefault("first_attempt", fmt(run_started))
        item["last_checked"] = item.get("last_checked", "")

        if url in current_success:
            item["last_success"] = fmt(current_success[url])
            item["status"] = "up"
            item["failures"] = 0
        else:
            last_success = parse_dt(item.get("last_success"))
            first_attempt = parse_dt(item.get("first_attempt")) or run_started
            age = (run_started - (last_success or first_attempt))
            item["status"] = "down" if age > THREE_DAYS else "degraded"
            item["failures"] = int(item.get("failures", 0)) + 1

        item["last_checked"] = fmt(run_started)
        if item["status"] == "down":
            moved.append(url)
            if url not in down:
                down.append(url)
        else:
            kept.append(url)

    URLS.parent.mkdir(parents=True, exist_ok=True)
    URLS.write_text("\n".join(unique(kept)) + ("\n" if kept else ""))
    DOWN.parent.mkdir(parents=True, exist_ok=True)
    DOWN.write_text("\n".join(unique(down)) + ("\n" if down else ""))
    save_json(STATE, state)

    phones = account_phone_map()
    # account_success is written by run_scraper's tracking wrapper.
    for url, account_id in successes.items():
        if url in state:
            state[url]["last_account"] = account_id
    save_json(STATE, state)

    # Local-only operational mapping. Never copy this into viewer/public.
    ACCOUNTS.parent.mkdir(parents=True, exist_ok=True)
    with ACCOUNTS.open("w", newline="") as f:
        fields = ["url", "account_id", "account_phone", "last_success", "last_checked", "status", "failures"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for url in unique(kept):
            item = state.get(url, {})
            aid = item.get("last_account", "")
            writer.writerow({
                "url": url,
                "account_id": aid,
                "account_phone": phones.get(aid, ""),
                "last_success": item.get("last_success", ""),
                "last_checked": item.get("last_checked", ""),
                "status": item.get("status", "unknown"),
                "failures": item.get("failures", 0),
            })

    return len(kept), moved, state


def append_history(run_started):
    run_started = parse_dt(run_started) or now()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT uid, eid, u, v, pv, raw, exp, fp, mirrors, s1, sl, mname, name FROM b").fetchall()
        success_urls = {r[0] for r in conn.execute("SELECT u FROM t WHERE ec=200 AND ts>=?", (run_started.strftime("%Y-%m-%d %H:%M:%S"),)).fetchall()}
    finally:
        conn.close()

    fields = ["run_ts", "uid", "eid", "url", "merchant", "name", "amount", "perceived_value", "expiry", "first_seen", "last_seen", "fingerprint", "mirrors"]
    existing = HISTORY.exists()
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not existing:
            writer.writeheader()
        for r in rows:
            if r[2] not in success_urls:
                continue
            writer.writerow({
                "run_ts": fmt(run_started), "uid": r[0], "eid": r[1], "url": r[2], "merchant": r[11] or "",
                "name": r[12] or "", "amount": r[3] or "", "perceived_value": r[4] or "", "expiry": r[10] or "",
                "first_seen": r[9] or "", "last_seen": r[9] or "", "fingerprint": r[7] or "", "mirrors": r[8] or "",
            })
    return len(rows)


def log_run(run_started, kept, moved):
    fields = ["run_ts", "active_sites", "moved_down", "history_rows"]
    existing = RUN_LOG.exists()
    with RUN_LOG.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not existing:
            writer.writeheader()
        writer.writerow({"run_ts": fmt(run_started), "active_sites": kept, "moved_down": len(moved), "history_rows": ""})


if __name__ == "__main__":
    started = os.environ.get("GOLF_RUN_STARTED") or now().isoformat()
    active, moved, _ = maintain_sites(started)
    history_rows = append_history(started)
    log_run(started, active, moved)
    print(f"Pipeline state: {active} active URLs, {len(moved)} moved to down.txt, {history_rows} current DB records considered")
