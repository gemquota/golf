"""Standalone CLI scraper with silent output and persistent pipeline maintenance."""
import os
import sys
from pathlib import Path

import db, scraper


def noop(*a, **kw):
    pass


db.initialize_database()

import server
server.STOPPED = False
server.PAUSED = False
server.IS_RUNNING = True

run_started = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
os.environ["GOLF_RUN_STARTED"] = run_started

scraper.run_scrape(
    on_update=noop,
    on_launcher=noop,
    on_completion=lambda s: print(
        f"\nDone: {s['successes']} sites, {s['total_bonuses']} bonuses, {s['new_bonuses']} new",
        file=sys.stderr,
    ),
)

# Maintain site health, down.txt, local account inventory and historical data.
import subprocess
subprocess.run([sys.executable, "maintain_pipeline.py"], check=True)

csv_files = sorted(Path("data").glob("bonuses_*.csv"))
if csv_files:
    latest = csv_files[-1]
    print(f"\n--- CSV: {latest} ---", file=sys.stderr)
    sys.stdout.write(latest.read_text())
