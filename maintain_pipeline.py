#!/usr/bin/env python3
"""Maintain URL health, quarantine history, account inventory and scrape exports.

Only URLs with a recorded attempt in the completed run are evaluated. A URL is
quarantined after failed attempts span at least 72 hours; skipped URLs never
accumulate failures. SQLite CURRENT_TIMESTAMP is UTC, so run markers are UTC.
"""
import csv
import datetime as dt
import json
import os
from pathlib import Path
import sqlite3
import tempfile

DB = Path("data/base.db")
URLS = Path("in/config/urls.txt")
DOWN = Path("in/config/down.txt")
STATE = Path("data/site_state.json")
ACCOUNT_SUCCESS = Path("data/account_success.json")
ACCOUNTS = Path("data/accounts.csv")
HISTORY = Path("data/bonus_history.csv")
RUN_LOG = Path("data/scrape_runs.csv")
THREE_DAYS = dt.timedelta(hours=72)
UTC = dt.timezone.utc


def now():
    return dt.datetime.now(UTC)


def parse_dt(value):
    if not value:
        return None
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        value = dt.datetime.fromisoformat(text)
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def fmt(value):
    parsed = value if isinstance(value, dt.datetime) else parse_dt(value)
    if not parsed:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat(timespec="seconds")


def sql_timestamp(value):
    parsed = value if isinstance(value, dt.datetime) else parse_dt(value)
    parsed = parsed or now()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def load_lines(path):
    if not path.exists():
        return []
    return [
        line.strip() for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def unique(values):
    return list(dict.fromkeys(values))


def load_json(path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
        return value if isinstance(value, type(default)) else default
    except (OSError, ValueError, TypeError):
        return default


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def save_json(path, value):
    atomic_write(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def save_lines(path, values):
    values = unique(values)
    atomic_write(path, "\n".join(values) + ("\n" if values else ""))


def account_phone_map():
    try:
        import config
        result = {}
        for section in config.config_parser.sections():
            if section.startswith("U"):
                user = config._env(f"GOLF_{section.upper()}_USER") or config.config_parser[section].get("u", "")
                if user:
                    result[section] = str(user)
        return result
    except Exception:
        return {}


def _attempts_for_run(run_started):
    if not DB.exists():
        return {}
    marker = sql_timestamp(run_started)
    conn = sqlite3.connect(DB)
    try:
        rows = conn.execute(
            "SELECT u, ec, ts FROM t WHERE ts IS NOT NULL AND ts >= ? ORDER BY ts",
            (marker,),
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        conn.close()
    attempts = {}
    for url, error_code, timestamp in rows:
        checked = parse_dt(timestamp)
        if url and checked:
            attempts[url] = {"error_code": error_code, "checked_at": checked}
    return attempts


def maintain_sites(run_started):
    """Update only attempted URLs; return active count, moved URLs, state and stats."""
    started = parse_dt(run_started) or now()
    urls = unique(load_lines(URLS))
    down = unique(load_lines(DOWN))
    state = load_json(STATE, {})
    successes = load_json(ACCOUNT_SUCCESS, {})
    attempts_by_url = _attempts_for_run(started)
    attempts = len(attempts_by_url)
    success_count = 0
    moved = []
    kept = []

    for url in urls:
        item = state.get(url)
        if not isinstance(item, dict):
            item = {}
        attempt = attempts_by_url.get(url)

        # A URL skipped by resume mode, pause/stop, or an incomplete run is
        # deliberately left unchanged: no attempt means no evidence of failure.
        if attempt is None:
            state[url] = item
            kept.append(url)
            continue

        checked = attempt["checked_at"]
        if checked < started:
            state[url] = item
            kept.append(url)
            continue

        if item.get("last_processed_attempt") == fmt(checked):
            state[url] = item
            kept.append(url)
            continue

        item["last_processed_attempt"] = fmt(checked)
        item["last_attempt"] = fmt(checked)
        error_code = attempt["error_code"]

        if error_code == 200:
            success_count += 1
            item["last_success"] = fmt(checked)
            item["status"] = "up"
            item["failures"] = 0
            item["first_failure_at"] = None
            item["last_failure_at"] = None
            # Recovery is explicit: the URL is active again and removed from
            # the current quarantine list; site_state retains its history.
            down = [entry for entry in down if entry != url]
            kept.append(url)
        else:
            first_failure = parse_dt(item.get("first_failure_at"))
            if not first_failure or item.get("status") == "up":
                first_failure = checked
            item["first_failure_at"] = fmt(first_failure)
            item["last_failure_at"] = fmt(checked)
            item["failures"] = int(item.get("failures", 0) or 0) + 1

            if checked - first_failure >= THREE_DAYS:
                item["status"] = "down"
                moved.append(url)
                if url not in down:
                    down.append(url)
            else:
                item["status"] = "degraded"
                kept.append(url)

        state[url] = item

    # Keep previously quarantined URLs in down.txt, including entries that
    # are not currently in urls.txt. Recovered active URLs are removed above.
    save_lines(URLS, kept)
    save_lines(DOWN, down)
    save_json(STATE, state)

    phones = account_phone_map()
    for url, account_id in successes.items():
        if url in state and isinstance(state[url], dict):
            state[url]["last_account"] = account_id
    save_json(STATE, state)

    ACCOUNTS.parent.mkdir(parents=True, exist_ok=True)
    fields = ["url", "account_id", "account_phone", "last_success", "last_checked", "status", "failures"]
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", dir=str(ACCOUNTS.parent), delete=False) as stream:
        temp_name = stream.name
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for url in kept:
            item = state.get(url, {})
            account_id = item.get("last_account", "")
            writer.writerow({
                "url": url, "account_id": account_id, "account_phone": phones.get(account_id, ""),
                "last_success": item.get("last_success", ""), "last_checked": item.get("last_attempt", ""),
                "status": item.get("status", "unknown"), "failures": item.get("failures", 0),
            })
    os.replace(temp_name, ACCOUNTS)
    return len(kept), moved, state, attempts, success_count


def append_history(run_started):
    started = parse_dt(run_started) or now()
    marker = sql_timestamp(started)
    if not DB.exists():
        return 0
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT uid,eid,u,v,pv,raw,exp,fp,mirrors,s1,sl,mname,name FROM b").fetchall()
        success_urls = {
            row[0] for row in conn.execute(
                "SELECT u FROM t WHERE ec=200 AND ts>=?", (marker,)
            ).fetchall()
        }
    finally:
        conn.close()

    fields = ["run_ts", "uid", "eid", "url", "merchant", "name", "amount", "perceived_value",
              "expiry", "first_seen", "last_seen", "fingerprint", "mirrors"]
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    existing = HISTORY.exists()
    with HISTORY.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if not existing:
            writer.writeheader()
        for row in rows:
            if row["u"] not in success_urls:
                continue
            writer.writerow({
                "run_ts": fmt(started), "uid": row["uid"], "eid": row["eid"], "url": row["u"],
                "merchant": row["mname"] or "", "name": row["name"] or "", "amount": row["v"] or "",
                "perceived_value": row["pv"] or "", "expiry": row["exp"] or "",
                "first_seen": row["s1"] or "", "last_seen": row["sl"] or "",
                "fingerprint": row["fp"] or "", "mirrors": row["mirrors"] or "",
            })
    return len(rows)


def log_run(run_started, kept, moved, attempts, successes, history_rows):
    fields = ["run_ts", "active_sites", "moved_down", "attempts", "successes", "history_rows"]
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    existing = RUN_LOG.exists()
    with RUN_LOG.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if not existing:
            writer.writeheader()
        writer.writerow({
            "run_ts": fmt(run_started), "active_sites": kept, "moved_down": len(moved),
            "attempts": attempts, "successes": successes, "history_rows": history_rows,
        })


def run_pipeline(run_started=None):
    started = parse_dt(run_started) or now()
    active, moved, _, attempts, successes = maintain_sites(started)
    history_rows = append_history(started)
    log_run(started, active, moved, attempts, successes, history_rows)
    print(
        f"Pipeline state: {active} active URLs, {len(moved)} moved to down.txt, "
        f"{attempts} attempted ({successes} successful), {history_rows} DB records considered"
    )
    return active, moved, attempts, successes, history_rows


if __name__ == "__main__":
    run_pipeline(os.environ.get("GOLF_RUN_STARTED"))
