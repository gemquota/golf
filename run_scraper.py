"""Standalone CLI scraper with silent output and persistent pipeline maintenance."""
import os
import sys
import shutil
from pathlib import Path

import db, scraper


def noop(*a, **kw):
    pass


db.initialize_database()

import server
server.STOPPED = False
server.PAUSED = False
server.IS_RUNNING = True

# SQLite CURRENT_TIMESTAMP is used by the scraper for site timestamps. Keep the
# run marker in the same naive clock format so long runs are still classified
# correctly as belonging to this execution.
run_started = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
os.environ["GOLF_RUN_STARTED"] = run_started

scraper.run_scrape(
    on_update=noop,
    on_launcher=noop,
    on_completion=lambda s: print(
        f"\nDone: {s['successes']} sites, {s['total_bonuses']} bonuses, {s['new_bonuses']} new",
        file=sys.stderr,
    ),
)

import subprocess
subprocess.run([sys.executable, "maintain_pipeline.py"], check=True)
subprocess.run([sys.executable, "build_exports.py"], check=True)

public = Path("viewer/public")
public.mkdir(parents=True, exist_ok=True)
for name in ("Dayne_Bonuses_Raw.csv", "bonus_history.csv", "scrape_runs.csv", "site_state.json"):
    source = Path("data") / name
    if source.exists():
        shutil.copy2(source, public / name.replace("_", "-").lower())

csv_files = sorted(Path("data").glob("bonuses_*.csv"))
if csv_files:
    latest = csv_files[-1]
    print(f"\n--- CSV: {latest} ---", file=sys.stderr)
    sys.stdout.write(latest.read_text())
