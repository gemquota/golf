#!/usr/bin/env python3
"""Read-only integrity audit for Golf's SQLite store and scrape artifacts."""
import argparse
import csv
import json
import sqlite3
import sys
import time
from pathlib import Path

REQUIRED_COLUMNS = {
    "sites": {"url", "error_code", "updated_at"},
    "bonuses": {"bonus_uid", "url", "amount", "perceived_value"},
    "scrape_runs": {
        "run_id", "created_at", "duration", "count", "new_count",
        "sum_perceived_value", "error_count", "active_sites",
        "moved_down", "attempts", "successes",
    },
}
HISTORY_COLUMNS = {"run_ts", "uid", "url"}
TEMP_MAX_AGE_SECONDS = 24 * 60 * 60


def issue(severity, code, message):
    return {"severity": severity, "code": code, "message": message}


def inspect_database(path):
    path = Path(path)
    issues = []
    if not path.is_file():
        return [issue("error", "database_missing", f"Database does not exist: {path}")]

    try:
        connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
        try:
            result = [row[0] for row in connection.execute("PRAGMA integrity_check")]
            if result != ["ok"]:
                issues.append(issue("error", "sqlite_integrity", "; ".join(result[:10])))
            tables = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            for table, required in REQUIRED_COLUMNS.items():
                if table not in tables:
                    issues.append(issue("error", "table_missing", f"Missing table: {table}"))
                    continue
                columns = {
                    row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                }
                missing = sorted(required - columns)
                if missing:
                    issues.append(issue(
                        "error", "columns_missing",
                        f"{table} is missing columns: {', '.join(missing)}",
                    ))

            if "scrape_runs" in tables:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(scrape_runs)")
                }
                if "run_id" in columns:
                    null_count = connection.execute(
                        "SELECT COUNT(*) FROM scrape_runs WHERE run_id IS NULL OR TRIM(run_id)=''"
                    ).fetchone()[0]
                    if null_count:
                        issues.append(issue(
                            "warning", "run_id_missing",
                            f"{null_count} historical scrape-run rows have no run_id",
                        ))
                    duplicates = connection.execute(
                        "SELECT run_id, COUNT(*) FROM scrape_runs "
                        "WHERE run_id IS NOT NULL GROUP BY run_id HAVING COUNT(*) > 1"
                    ).fetchall()
                    if duplicates:
                        issues.append(issue(
                            "error", "run_id_duplicate",
                            f"{len(duplicates)} duplicate scrape-run IDs found",
                        ))
                if {"duration", "attempts", "successes"} <= columns:
                    invalid = connection.execute(
                        "SELECT COUNT(*) FROM scrape_runs WHERE "
                        "duration < 0 OR attempts < 0 OR successes < 0 OR successes > attempts"
                    ).fetchone()[0]
                    if invalid:
                        issues.append(issue(
                            "error", "run_metrics_invalid",
                            f"{invalid} scrape-run rows contain impossible metrics",
                        ))

            for row in connection.execute("PRAGMA foreign_key_check"):
                issues.append(issue(
                    "error", "foreign_key_violation",
                    f"Foreign-key violation in table {row[0]} row {row[1]}",
                ))
        finally:
            connection.close()
    except (sqlite3.Error, OSError) as exc:
        issues.append(issue("error", "database_unreadable", str(exc)))
    return issues


def inspect_history(path):
    path = Path(path)
    if not path.exists():
        return [issue("warning", "history_missing", f"History CSV not found: {path}")]
    if path.stat().st_size == 0:
        return [issue("error", "history_empty", f"History CSV is empty: {path}")]

    issues = []
    seen = set()
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            fields = set(reader.fieldnames or [])
            missing = sorted(HISTORY_COLUMNS - fields)
            if missing:
                return [issue(
                    "error", "history_columns_missing",
                    f"History CSV is missing columns: {', '.join(missing)}",
                )]
            for line_number, row in enumerate(reader, start=2):
                if None in row:
                    issues.append(issue(
                        "error", "history_malformed_row",
                        f"History CSV row {line_number} has more fields than its header",
                    ))
                    continue
                run_ts, uid = (row.get("run_ts") or "").strip(), (row.get("uid") or "").strip()
                if not run_ts or not uid or not (row.get("url") or "").strip():
                    issues.append(issue(
                        "error", "history_key_missing",
                        f"History CSV row {line_number} is missing run_ts, uid, or url",
                    ))
                    continue
                key = (run_ts, uid)
                if key in seen:
                    issues.append(issue(
                        "error", "history_duplicate",
                        f"Duplicate history key at row {line_number}: {run_ts} / {uid}",
                    ))
                seen.add(key)
    except (OSError, csv.Error, UnicodeError) as exc:
        issues.append(issue("error", "history_unreadable", str(exc)))
    return issues


def inspect_temporary_files(directory, now=None):
    directory = Path(directory)
    if not directory.exists():
        return []
    current = time.time() if now is None else now
    issues = []
    for path in sorted(directory.glob("tmp_*.csv")):
        try:
            age = current - path.stat().st_mtime
        except OSError:
            continue
        if age >= TEMP_MAX_AGE_SECONDS:
            issues.append(issue(
                "warning", "stale_worker_fragment",
                f"Temporary worker fragment is {age / 3600:.1f} hours old: {path}",
            ))
    return issues


def audit(db_path="data/base.db", history_path="data/bonus_history.csv",
          temp_dir="data", now=None):
    return (
        inspect_database(db_path)
        + inspect_history(history_path)
        + inspect_temporary_files(temp_dir, now=now)
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/base.db", help="SQLite database path")
    parser.add_argument("--history", default="data/bonus_history.csv", help="bonus history CSV")
    parser.add_argument("--tmp-dir", default="data", help="worker temporary directory (scraper writes data/tmp_*.csv)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)
    issues = audit(args.db, args.history, args.tmp_dir)
    errors = sum(item["severity"] == "error" for item in issues)
    warnings = sum(item["severity"] == "warning" for item in issues)
    if args.json:
        print(json.dumps({
            "ok": errors == 0, "errors": errors, "warnings": warnings, "issues": issues,
        }, indent=2))
    else:
        if not issues:
            print("Integrity audit passed: no errors or warnings.")
        else:
            for item in issues:
                print(
                    f'{item["severity"].upper()} [{item["code"]}] {item["message"]}'
                )
            print(f"Integrity audit: {errors} error(s), {warnings} warning(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
