import sys, threading
from pathlib import Path

import config, db, scraper, server, terminal


def _on_completion(stats):
    terminal.print_completion(stats)
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

    if "-h" in sys.argv:
        print("Usage: python main.py [-v min|med|max] [-r] [-s]")
        sys.exit(0)

    server.IS_RUNNING = True

    callbacks = {
        "on_update": terminal.update_display,
        "on_launcher": terminal.print_launcher,
        "on_completion": _on_completion
    }

    threading.Thread(target=scraper.run_scrape, kwargs=callbacks, daemon=True).start()
    server.start_server()

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        db.log_event("FATAL", "500", str(exc))
        print(f"FATAL: {exc}", file=sys.stderr)
