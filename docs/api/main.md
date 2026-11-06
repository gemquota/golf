# Application entry point

`main.py` is the compatibility entry point for starting the scraper application. The maintained command interface lives in `golf/cli.py`; new commands and orchestration should be added there rather than expanding the legacy entry point.

## Runtime flow

1. Initialize the SQLite schema through `db.initialize_database()`.
2. Start the dashboard server.
3. Run the scraper in its worker thread.
4. Report completion and shutdown through the application lifecycle.

See [CLI](../../golf/cli.py), [database](../../db.py), [scraper](../../scraper.py), and [dashboard](../../server.py).
