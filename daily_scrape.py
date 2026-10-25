#!/usr/bin/env python3
"""Headless entry point for the scheduled daily scrape."""
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import db
import scraper
import server


def main():
    Path("data").mkdir(parents=True, exist_ok=True)
    db.initialize_database()
    started = datetime.now(timezone.utc).replace(microsecond=0)
    started_sql = started.strftime("%Y-%m-%d %H:%M:%S")
    server.STOPPED = False
    server.PAUSED = False
    server.IS_RUNNING = True

    print(f"Daily scrape started at {started_sql} UTC", flush=True)
    scraper.run_scrape()
    if server.STOPPED:
        raise RuntimeError("Scrape was stopped before the daily history could be finalized")

    csv_files = list(Path("data").glob("bonuses_*.csv"))
    if not csv_files:
        raise RuntimeError("Scraper did not produce a bonuses_*.csv file")
    current_csv = max(csv_files, key=lambda path: path.stat().st_mtime)

    # Refresh the current-viewer CSVs from the completed run's database.
    subprocess.run(
        [sys.executable, "export_viewer_data.py", "viewer/public"],
        check=True
    )
    local_date = datetime.now(ZoneInfo("Australia/Brisbane")).date().isoformat()
    subprocess.run([
        sys.executable, "bonus_history.py",
        "--csv", str(current_csv),
        "--started-at", started_sql,
        "--date", local_date,
    ], check=True)
    print(f"Daily scrape complete. Snapshot date: {local_date}", flush=True)


if __name__ == "__main__":
    main()
