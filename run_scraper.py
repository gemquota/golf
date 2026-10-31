"""Standalone CLI scraper with the same post-run maintenance as the dashboard."""
import datetime
import os
import shutil
import subprocess
import sys
from pathlib import Path

import db
import scraper


def noop(*args, **kwargs):
    pass


def main():
    Path("data").mkdir(parents=True, exist_ok=True)
    db.initialize_database()
    import server
    server.STOPPED = False
    server.PAUSED = False
    server.IS_RUNNING = True

    os.environ["GOLF_RUN_STARTED"] = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat(timespec="seconds")

    scraper.run_scrape(
        on_update=noop,
        on_launcher=noop,
        on_completion=lambda stats: print(
            f"\nDone: {stats['successes']} sites, {stats['total_bonuses']} bonuses, "
            f"{stats['new_bonuses']} new",
            file=sys.stderr,
        ),
    )

    import maintain_pipeline
    maintain_pipeline.run_pipeline(os.environ["GOLF_RUN_STARTED"])
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
        sys.stdout.write(latest.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
