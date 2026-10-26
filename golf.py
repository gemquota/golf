#!/usr/bin/env python3
"""Canonical CLI for scraping, maintenance, exports, and interactive operation."""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)


def run_stage(script: str, *args: str) -> None:
    command = [sys.executable, str(ROOT / script), *args]
    print(f"\n==> {' '.join([Path(sys.executable).name, script, *args])}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def run_pipeline(run_started: str, publish: bool = True, analysis: bool = True) -> None:
    """Run the established post-scrape stages in dependency order."""
    os.environ["GOLF_RUN_STARTED"] = run_started
    run_stage("maintain_pipeline.py")
    run_stage("build_exports.py")
    cleaned = ROOT / "data" / "Dayne_Bonuses_Cleaned.csv"
    run_stage("clean_bonuses.py", str(ROOT / "data" / "Dayne_Bonuses.csv"))
    if analysis:
        run_stage("compare_bonus_scores.py", str(cleaned))
    if publish:
        run_stage("publish_viewer.py")


def _prepare_database():
    import db
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    db.initialize_database()


def _set_scraper_args(resume: bool, shuffle: bool, verbosity: str) -> None:
    args = ["golf.py"]
    if resume:
        args.append("-r")
    if shuffle:
        args.append("-s")
    if verbosity:
        args.extend(["-v", verbosity])
    sys.argv = args


def scrape(args) -> int:
    import db
    import scraper
    import server

    _prepare_database()
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    os.environ["GOLF_RUN_STARTED"] = started
    _set_scraper_args(args.resume, args.shuffle, args.verbosity)
    server.STOPPED = False
    server.PAUSED = False
    server.IS_RUNNING = True

    def completed(stats):
        print(
            f"\nScrape complete: {stats.get('successes', 0)} sites succeeded; "
            f"{stats.get('failures', 0)} failed; "
            f"{stats.get('total_bonuses', 0)} positive-amount bonuses; "
            f"{stats.get('new_bonuses', 0)} new records.",
            flush=True,
        )
        if args.no_pipeline:
            return
        try:
            run_pipeline(started, publish=not args.no_publish, analysis=not args.no_analysis)
        except Exception as exc:
            db.log_event("PIPELINE_ERROR", "golf", str(exc))
            print(f"Post-scrape pipeline failed: {exc}", file=sys.stderr, flush=True)

    try:
        scraper.run_scrape(
            on_update=None,
            on_launcher=lambda *a: print(f"Starting scrape: {a}", flush=True),
            on_completion=completed,
        )
    except KeyboardInterrupt:
        server.STOPPED = True
        db.log_event("INTERRUPTED", "golf", "Scrape interrupted by user")
        return 130
    return 0


def interactive(args) -> int:
    import db
    import config
    import scraper
    import server
    import terminal

    _prepare_database()
    if args.resume or args.shuffle or args.verbosity:
        _set_scraper_args(args.resume, args.shuffle, args.verbosity)
    else:
        sys.argv = ["golf.py"]

    def completed(stats):
        terminal.print_completion(stats)
        if args.no_pipeline:
            return
        started = os.environ.get("GOLF_RUN_STARTED") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            run_pipeline(started, publish=not args.no_publish, analysis=not args.no_analysis)
        except Exception as exc:
            db.log_event("PIPELINE_ERROR", "golf", str(exc))
            print(f"Post-scrape pipeline failed: {exc}", file=sys.stderr)

    os.environ.setdefault("GOLF_RUN_STARTED", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    server.IS_RUNNING = True
    callbacks = {
        "on_update": terminal.update_display,
        "on_launcher": terminal.print_launcher,
        "on_completion": completed,
    }
    threading.Thread(target=scraper.run_scrape, kwargs=callbacks, daemon=True).start()
    server.start_server()
    return 0


def _latest_recorded_run() -> str | None:
    path = ROOT / "data" / "scrape_runs.csv"
    if not path.exists():
        return None
    try:
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        if rows:
            return rows[-1].get("run_ts") or None
    except (OSError, csv.Error):
        return None
    return None


def pipeline(args) -> int:
    _prepare_database()
    started = os.environ.get("GOLF_RUN_STARTED") or _latest_recorded_run()
    if not started:
        raise RuntimeError("No recorded scrape run exists. Run the full scrape first, or set GOLF_RUN_STARTED to the run start time.")
    run_pipeline(started, publish=not args.no_publish, analysis=not args.no_analysis)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="golf.py",
        description="Scrape sites, maintain history, build exports, and publish the bonus viewer.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_pipeline_flags(p):
        p.add_argument("--no-pipeline", action="store_true", help="Scrape only; skip post-processing.")
        p.add_argument("--no-publish", action="store_true", help="Build local outputs but do not push viewer CSVs.")
        p.add_argument("--no-analysis", action="store_true", help="Skip the separate score comparison report.")

    p_scrape = sub.add_parser("scrape", help="Run a full scrape followed by maintenance and exports.")
    p_scrape.add_argument("-r", "--resume", action="store_true", help="Skip URLs successfully scraped in the last day.")
    p_scrape.add_argument("-s", "--shuffle", action="store_true", help="Shuffle URL order.")
    p_scrape.add_argument("-v", "--verbosity", choices=["min", "med", "max"], default=None,
                          help="Set scraper verbosity; max records raw response JSON.")
    add_pipeline_flags(p_scrape)
    p_scrape.set_defaults(handler=scrape)

    p_interactive = sub.add_parser("interactive", help="Run the dashboard and interactive terminal UI.")
    p_interactive.add_argument("-r", "--resume", action="store_true")
    p_interactive.add_argument("-s", "--shuffle", action="store_true")
    p_interactive.add_argument("-v", "--verbosity", choices=["min", "med", "max"], default=None)
    add_pipeline_flags(p_interactive)
    p_interactive.set_defaults(handler=interactive)

    p_pipeline = sub.add_parser("pipeline", help="Run maintenance, analysis exports, and optional publishing without scraping.")
    p_pipeline.add_argument("--no-publish", action="store_true")
    p_pipeline.add_argument("--no-analysis", action="store_true")
    p_pipeline.set_defaults(handler=pipeline)

    p_export = sub.add_parser("export", help="Regenerate viewer CSVs locally without committing or pushing.")
    p_export.set_defaults(handler=lambda args: (run_stage("publish_viewer.py", "--export-only") or 0))

    p_publish = sub.add_parser("publish", help="Regenerate viewer CSVs and publish them.")
    p_publish.set_defaults(handler=lambda args: (run_stage("publish_viewer.py") or 0))
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args) or 0)
    except subprocess.CalledProcessError as exc:
        print(f"Stage failed ({exc.returncode}): {exc.cmd}", file=sys.stderr)
        return exc.returncode or 1
    except Exception as exc:
        try:
            import db
            db.log_event("FATAL", "golf", str(exc))
        except Exception:
            pass
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
