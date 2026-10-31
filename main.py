import datetime
import os
import sys
import threading
from pathlib import Path

import config, db, scraper, server, terminal


def _on_completion(stats):
    terminal.print_completion(stats)
    try:
        import maintain_pipeline
        maintain_pipeline.run_pipeline(os.environ.get("GOLF_RUN_STARTED"))
    except Exception as exc:
        db.log_event("MAINTENANCE_ERROR", "maintain_pipeline", str(exc))

    if not config.config_parser.getboolean("SETTINGS", "auto_publish", fallback=True):
        return
    try:
        import publish_viewer
        publish_viewer.main()
    except Exception as exc:
        db.log_event("PUBLISH_ERROR", "publish_viewer", str(exc))


def main():
    Path("data").mkdir(parents=True, exist_ok=True)
    db.initialize_database()

    if "-h" in sys.argv or "--help" in sys.argv:
        print("Usage: python main.py [-v min|med|max] [-r] [-s]")
        return

    # SQLite CURRENT_TIMESTAMP is UTC. Use an aware UTC run marker and let
    # maintain_pipeline normalize it before comparing with SQLite timestamps.
    os.environ["GOLF_RUN_STARTED"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    server.STOPPED = False
    server.PAUSED = False
    server.IS_RUNNING = True

    callbacks = {
        "on_update": terminal.update_display,
        "on_launcher": terminal.print_launcher,
        "on_completion": _on_completion,
    }
    threading.Thread(target=scraper.run_scrape, kwargs=callbacks, daemon=True).start()
    server.start_server()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        try:
            db.log_event("FATAL", "main", str(exc))
        except Exception:
            pass
        print(f"FATAL: {exc}", file=sys.stderr)
