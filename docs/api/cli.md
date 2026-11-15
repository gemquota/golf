# Application CLI

The supported application entry point is the `golf` package:

```sh
python -m golf interactive
python -m golf scrape
python -m golf scrape --no-pipeline
python -m golf pipeline --no-publish
python -m golf export --viewer
python -m golf migrate
```

The CLI owns argument parsing and orchestration in `golf/cli.py`. The
interactive command starts the terminal renderer and local FastAPI dashboard;
the scrape command runs headlessly; pipeline and export commands operate on
the existing local database without requiring another scrape.

The former root-level `main.py`, `run_scraper.py`, and `run_fast.py`
compatibility shims have been retired. Their behaviors map to the commands
above. On-device users should start the dashboard with `bash device_run.sh`.

See [the schema migration guide](../migrations.md), [scraper orchestration](scraper.md),
and [dashboard server](server.md).
