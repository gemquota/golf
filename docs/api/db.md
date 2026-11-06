# Database API

`db.py` owns SQLite connection management, schema initialization/migration, session persistence, event logging, full-text search, and shared bonus utility functions.

## Data model

- `sites`: configured site metadata and most recent check status.
- `bonuses`: canonical discovered bonus records and raw source payloads.
- `sessions`: local account session material.
- `scrape_runs`: schema support for run summaries.
- `logs`: application diagnostics.
- `bonuses_fts`: FTS5 index over searchable bonus fields.

## Operational notes

The database is local runtime state, not the durable publication history. Treat session rows as credentials: keep database files out of version control and restrict local file permissions.

See [db.py](../../db.py).
