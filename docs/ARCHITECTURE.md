# Golf Scraper Architecture

## System boundaries

- `golf/cli.py` is the command-line entry point and dispatches scrape, export, and maintenance commands.
- `scraper.py` coordinates site/account work and worker threads.
- `network.py` owns HTTP sessions, proxy routing, login, merchant API requests, and response parsing.
- `config.py` resolves local configuration and environment overrides.
- `db.py` owns SQLite schema initialization, migrations, sessions, bonus records, and diagnostics.
- `terminal.py` and `server.py` are presentation/control surfaces. They consume progress events; they should not own scrape or scoring policy.
- `bonus_scoring.py` owns the scoring formula and confidence/source semantics.
- `export_csv.py` owns shared raw-payload normalization, site/dataset scoring context, and common CSV serialization.
- `export_viewer_data.py` adapts canonical records into the active Vite viewer's published CSV schemas.

## Data flow

1. The CLI loads configuration and initializes the local SQLite database.
2. The scraper schedules site/account tasks and delegates HTTP work to the network module.
3. Workers parse site responses and persist canonical bonus/site records in SQLite.
4. Worker progress is sent to the terminal renderer and dashboard event queue.
5. Export commands read canonical database rows. Shared normalization and scoring context are calculated in `export_csv.py`; scoring policy is applied by `bonus_scoring.py`.
6. The viewer exporter performs viewer-specific column mapping and site rollups, then writes snapshots under `viewer/public/`.
7. `daily_scrape.py` and `publish_viewer.py` coordinate scheduled scraping and publication. The historical `scrape_and_deploy.sh` wrapper is scrape-only; it no longer attempts to build or package a separate `dayne-bonuses-viewer` checkout.

## Export ownership

There is one canonical implementation for raw JSON decoding and key normalization, finite-number parsing and URL hostname normalization, site and dataset median calculation for score imputation, and score calculation with confidence/source metadata.

Exporters own only their output schemas and presentation-specific aggregation. Do not duplicate scoring context or fallback logic in a serializer.

## Runtime state and publication

SQLite is local/per-run runtime state. Published viewer snapshots and bonus history are explicit files under `viewer/public/`; these are not interchangeable with the runtime database. Keep database files, session material, local config, and generated caches out of version control.

## Documentation

The `docs/api/` pages describe module responsibilities and stable entry points. They intentionally avoid generated line numbers and call-count metrics, which become stale after ordinary refactoring. Source code remains authoritative for exact signatures and behavior.
