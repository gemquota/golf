# API reference index

These references describe module ownership and stable integration boundaries. They deliberately avoid source line numbers and generated call-count metrics because those become stale on routine edits.

## Application

- [CLI and entry point](main.md)
- [Configuration](config.md)
- [Scraper orchestration](scraper.md)
- [Network and authentication](network.md)
- [SQLite persistence](db.md)
- [Terminal interface](terminal.md)
- [Dashboard server](server.md)

## Data and exports

- [Bonus scoring](bonus_scoring.md)
- [Canonical CSV export pipeline](export_csv.md)
- [Viewer export adapter](export_viewer_data.md)

Exact function signatures and runtime behavior are defined by the linked source files. Update the relevant page whenever a module's responsibilities or data contracts change.
