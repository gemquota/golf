# Database API

`db.py` owns SQLite connection management, schema initialization/migration, session persistence, event logging, full-text search, and shared bonus utility functions.

## Data model

- `sites`: configured site metadata and most recent check status.
- `bonuses`: canonical discovered bonus records and raw source payloads.
- `sessions`: local account session material.
- `scrape_runs`: idempotent per-run metrics, including duration, bonus counts, perceived-value total, errors, active sites, and attempt/success totals.
- `logs`: application diagnostics.
- `bonuses_fts`: FTS5 index over searchable bonus fields.

## Run-history contract

`maintain_pipeline.record_run()` writes one row per UTC run-start marker. A unique index on `run_id` makes retries idempotent. Legacy duplicate run IDs are reduced to their latest row during schema initialization. The old `data/scrape_runs.csv` side log is no longer written.

The existing `count`, `new_count`, `sum_perceived_value`, and `error_count` columns retain their bonus/error meanings. Additional operational columns record active sites, moved-down URLs, attempts, and successes.

## Operational notes

The database is local runtime state and the canonical store for scrape-run summaries. The daily publication workflow separately commits viewer snapshots and bonus history. Treat session rows as credentials: keep database files out of version control and restrict local file permissions.

See [db.py](../../db.py) and [maintain_pipeline.py](../../maintain_pipeline.py).
