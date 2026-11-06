#!/usr/bin/env python3
"""Canonical CLI for scraping, maintenance, exports, migration and interactive use."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _chdir_root() -> None:
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def run_stage(script: str, *args: str) -> None:
    command = [sys.executable, str(ROOT / script), *args]
    print(f"\n==> {' '.join([Path(sys.executable).name, script, *args])}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def _prepare_database():
    import db
    (ROOT / "data").mkdir(parents=True, exist_ok=True)
    db.initialize_database()


def _set_scraper_flags(resume: bool, shuffle: bool, verbosity: str | None) -> None:
    args = ["golf"]
    if resume:
        args.append("-r")
    if shuffle:
        args.append("-s")
    if verbosity:
        args.extend(["-v", verbosity])
    sys.argv = args


def cmd_migrate(_args) -> int:
    _prepare_database()
    import db
    db.migrate_ungolf_schema()
    print("Migration complete (idempotent). See MIGRATION.md.")
    return 0


def cmd_scrape(args) -> int:
    import db
    import scraper
    import server

    _prepare_database()
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    os.environ["GOLF_RUN_STARTED"] = started
    _set_scraper_flags(args.resume, args.shuffle, args.verbosity)
    server.STOPPED = False
    server.PAUSED = False
    server.IS_RUNNING = True

    pipeline_failed = [False]

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
            import maintain_pipeline
            maintain_pipeline.run_pipeline(started)
            run_stage("build_exports.py")
            if not args.no_publish:
                run_stage("publish_viewer.py")
        except Exception as exc:
            pipeline_failed[0] = True
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
    return 1 if pipeline_failed[0] else 0


def cmd_run(args) -> int:
    """Alias for scrape (primary non-interactive entry)."""
    return cmd_scrape(args)


def cmd_interactive(args) -> int:
    import db
    import scraper
    import server
    import terminal

    _prepare_database()
    if args.resume or args.shuffle or args.verbosity:
        _set_scraper_flags(args.resume, args.shuffle, args.verbosity)
    else:
        sys.argv = ["golf"]

    def completed(stats):
        terminal.print_completion(stats)
        if args.no_pipeline:
            return
        started = os.environ.get("GOLF_RUN_STARTED") or datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            import maintain_pipeline
            maintain_pipeline.run_pipeline(started)
            if not args.no_publish:
                run_stage("publish_viewer.py")
        except Exception as exc:
            db.log_event("PIPELINE_ERROR", "golf", str(exc))
            print(f"Post-scrape pipeline failed: {exc}", file=sys.stderr)

    os.environ.setdefault(
        "GOLF_RUN_STARTED",
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    server.STOPPED = False
    server.PAUSED = False
    server.IS_RUNNING = True
    callbacks = {
        "on_update": terminal.update_display,
        "on_launcher": terminal.print_launcher,
        "on_completion": completed,
    }
    threading.Thread(target=scraper.run_scrape, kwargs=callbacks, daemon=True).start()
    server.start_server()
    return 0


def cmd_export(args) -> int:
    _prepare_database()
    from export_csv import build_analysis_exports, export_db_to_csv
    n = build_analysis_exports()
    print(f"Analysis exports written ({n} bonuses).")
    if args.simple:
        export_db_to_csv()
    if args.viewer:
        run_stage("export_viewer_data.py")
    return 0


def cmd_pipeline(args) -> int:
    _prepare_database()
    started = os.environ.get("GOLF_RUN_STARTED")
    import maintain_pipeline
    maintain_pipeline.run_pipeline(started)
    run_stage("build_exports.py")
    if not args.no_publish:
        run_stage("publish_viewer.py")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="golf",
        description="Scrape sites, maintain history, build exports, migrate schema, and run the dashboard.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_scrape_flags(p):
        p.add_argument("-r", "--resume", action="store_true", help="Skip URLs successfully scraped in the last day.")
        p.add_argument("-s", "--shuffle", action="store_true", help="Shuffle URL order.")
        p.add_argument("-v", "--verbosity", choices=["min", "med", "max"], default=None,
                       help="Set scraper verbosity; max records raw response JSON.")
        p.add_argument("--no-pipeline", action="store_true", help="Scrape only; skip post-processing.")
        p.add_argument("--no-publish", action="store_true", help="Build local outputs but do not push viewer CSVs.")

    p_run = sub.add_parser("run", help="Full non-interactive scrape (alias of scrape).")
    add_scrape_flags(p_run)
    p_run.set_defaults(handler=cmd_run)

    p_scrape = sub.add_parser("scrape", help="Full non-interactive scrape followed by maintenance/exports.")
    add_scrape_flags(p_scrape)
    p_scrape.set_defaults(handler=cmd_scrape)

    p_interactive = sub.add_parser("interactive", help="Dashboard + terminal UI.")
    add_scrape_flags(p_interactive)
    p_interactive.set_defaults(handler=cmd_interactive)

    p_export = sub.add_parser("export", help="Regenerate analysis/viewer CSVs locally (no network scrape).")
    p_export.add_argument("--simple", action="store_true", help="Also write the flat Dayne_Bonuses.csv.")
    p_export.add_argument("--viewer", action="store_true", help="Also run export_viewer_data.py.")
    p_export.set_defaults(handler=cmd_export)

    p_migrate = sub.add_parser("migrate", help="Apply idempotent schema renames to the SQLite DB.")
    p_migrate.set_defaults(handler=cmd_migrate)

    p_pipeline = sub.add_parser("pipeline", help="Run maintenance and exports without scraping.")
    p_pipeline.add_argument("--no-publish", action="store_true")
    p_pipeline.set_defaults(handler=cmd_pipeline)

    return parser


def main(argv=None) -> int:
    _chdir_root()
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
