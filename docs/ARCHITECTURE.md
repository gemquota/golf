# Golf Scraper Architecture

## System boundaries

- `golf/cli.py` is the command-line entry point and dispatches scrape, export, and maintenance commands.
- `scraper.py` coordinates site/account work and worker threads.
- `network.py` owns HTTP sessions, proxy routing, login, merchant API requests, and response parsing.
- `config.py` resolves local configuration and environment overrides.
- `db.py` owns SQLite schema initialization, migrations, sessions, bonus records, scrape-run summaries, and diagnostics.
- `terminal.py` and `server.py` are presentation/control surfaces. They consume progress events; they should not own scrape or scoring policy.
- `bonus_scoring.py` owns the scoring formula and confidence/source semantics.
- `export_csv.py` owns shared raw-payload normalization, site/dataset scoring context, and common CSV serialization.
- `export_viewer_data.py` adapts canonical records into the active Vite viewer's published CSV schemas.
- `maintain_pipeline.py` maintains URL health and writes idempotent run summaries into SQLite.

## Data flow

1. The CLI loads configuration and initializes the local SQLite database.
2. The scraper schedules site/account tasks and delegates HTTP work to the network module.
3. Workers parse site responses and persist canonical bonus/site records in SQLite.
4. Worker progress is sent to the terminal renderer and dashboard event queue.
5. Export commands read canonical database rows. Shared normalization and scoring context are calculated in `export_csv.py`; scoring policy is applied by `bonus_scoring.py`.
6. The viewer exporter performs viewer-specific column mapping and site rollups, then writes snapshots under `viewer/public/`.
7. `daily_scrape.py` and `publish_viewer.py` coordinate scheduled scraping and publication. The historical `scrape_and_deploy.sh` wrapper runs scraping and the standalone analysis cleaner; it no longer attempts to build or package a separate `dayne-bonuses-viewer` checkout.
8. `maintain_pipeline.py` records one row per completed run in `scrape_runs`, keyed by the UTC run-start marker. Replaying the same run marker replaces the prior summary instead of duplicating it.

## Export ownership

There is one canonical implementation for raw JSON decoding and key normalization, finite-number parsing and URL hostname normalization, site and dataset median calculation for score imputation, and score calculation with confidence/source metadata.

Exporters own only their output schemas and presentation-specific aggregation. Do not duplicate scoring context or fallback logic in a serializer.

## Runtime state and publication

SQLite is local/per-run runtime state and the single source of truth for scrape-run summaries. The old parallel `data/scrape_runs.csv` writer has been removed. Published viewer snapshots and bonus history are explicit files under `viewer/public/`; these are not interchangeable with the runtime database. Keep database files, session material, local config, and generated caches out of version control.

The standalone `clean_bonuses.py` utility uses the Python standard library and the shared finite-number parser from `bonus_scoring.py`. It does not install or import pandas/NumPy and does not mutate its input snapshot.

The duplicate icon assets are intentionally retained: `viewer/icon.svg` is referenced by the external `viewer/app.json` package manifest, while `viewer/public/icon.svg` is a Vite public asset. They serve separate packaging contexts and should not be collapsed without changing the packaging contract.

## Documentation

The `docs/api/` pages describe module responsibilities and stable entry points. They intentionally avoid generated line numbers and call-count metrics, which become stale after ordinary refactoring. Source code remains authoritative for exact signatures and behavior.
