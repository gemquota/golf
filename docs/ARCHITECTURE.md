# Golf Scraper Architecture

## Runtime structure

- `golf/` is the canonical CLI package.
- Root-level modules implement scraping, persistence, export, and maintenance.
- `server.py` provides the local FastAPI dashboard and control API.
- `terminal.py` renders the interactive terminal view.
- `viewer/` is the separate Vite static viewer deployed to GitHub Pages.

## Data flow

1. The CLI initializes the local SQLite database and starts the scraper.
2. Workers fetch configured URLs, authenticate to target sites, sync bonus data, and persist local records.
3. The export pipeline generates analysis and viewer CSVs.
4. The daily workflow compares each scrape with `viewer/public/bonus-history.json`, the durable release-history store.
5. The workflow commits public viewer outputs and release-history JSON, then triggers Pages deployment.

GitHub Actions creates SQLite for each run and does not commit it between scheduled runs.

## Security boundaries

- Dashboard API authentication is mandatory and fails closed.
- Incorrect credentials are rejected with HTTP 401.
- The config API exposes only editable delay settings, never account credentials or secrets.
- WebSocket access requires a short-lived, single-use ticket from an authenticated API request.
- The server binds to `127.0.0.1` by default. Set `GOLF_BIND_HOST` only for an intentional, protected network deployment.
- Local SQLite files contain reusable target-site session data. They are ignored by Git and created with owner-only file permissions where supported.
- Real account credentials belong in `in/config/config.local.ini` or environment variables, never in tracked files.

## Persistence

- SQLite stores local site/bonus records, cached session data, and application logs.
- `viewer/public/bonus-history.json` stores the scheduled release baseline and observations.
- CSV files are exports, not the authoritative release-history store.
