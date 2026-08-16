"""Standalone CLI scraper — outputs CSV to stdout, no server."""
import csv, sys, os, threading, time

# Suppress terminal output
os.environ["PYTHONIOENCODING"] = "utf-8"

import db, scraper, config

# Monkey-patch terminal callbacks to be silent
def noop(*a, **kw): pass

db.initialize_database()

# Ensure stopped flag is cleared
import server
server.STOPPED = False
server.PAUSED = False
server.IS_RUNNING = True

# Run scraper with silent callbacks
scraper.run_scrape(
    on_update=noop,
    on_launcher=noop,
    on_completion=lambda s: print(f"\nDone: {s['successes']} sites, {s['total_bonuses']} bonuses, {s['new_bonuses']} new", file=sys.stderr)
)

# Find latest CSV
from pathlib import Path
csv_files = sorted(Path("data").glob("bonuses_*.csv"))
if csv_files:
    latest = csv_files[-1]
    print(f"\n--- CSV: {latest} ---", file=sys.stderr)
    sys.stdout.write(latest.read_text())
