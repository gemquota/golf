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

# Maintain site health, down list, local account inventory and historical data.
import subprocess
subprocess.run([sys.executable, "maintain_pipeline.py"], check=True)

# Preserve an explicit raw snapshot before the legacy shell export rewrites
# data/Dayne_Bonuses.csv. This gives the pipeline three durable layers:
# raw scraped data -> enriched calculations -> cleaned presentation.
subprocess.run([sys.executable, "build_exports.py"], check=True)

# Feed the static viewer with the historical operational datasets. The legacy
# deployment script will also copy the enriched and cleaned current CSVs.
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
