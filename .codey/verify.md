# Verify: I-ungolf-refactor

Verified: 2026-11-03 06:14:23 AEST
Method: fresh shell, TMPDIR=/tmp/golf-verify-lpEd9C, `python3 -m unittest discover -s tests -v`

## Suite result

```
test_export_subcommand_empty_db (test_cli_smoke.CliSmokeTests.test_export_subcommand_empty_db) ... ok
test_export_viewer_flag_invokes_stage (test_cli_smoke.CliSmokeTests.test_export_viewer_flag_invokes_stage) ... ok
test_interactive_wires_scraper_thread_and_server (test_cli_smoke.CliSmokeTests.test_interactive_wires_scraper_thread_and_server) ... ok
test_migrate_subcommand (test_cli_smoke.CliSmokeTests.test_migrate_subcommand) ... ok
test_parser_exposes_required_subcommands (test_cli_smoke.CliSmokeTests.test_parser_exposes_required_subcommands) ... ok
test_pipeline_subcommand_invokes_maintain (test_cli_smoke.CliSmokeTests.test_pipeline_subcommand_invokes_maintain) ... ok
test_scrape_and_run_accept_flags_without_network (test_cli_smoke.CliSmokeTests.test_scrape_and_run_accept_flags_without_network) ... Analysis exports written (0 bonuses).
Analysis exports written (0 bonuses).

Scrape complete: 0 sites succeeded; 0 failed; 0 positive-amount bonuses; 0 new records.

Scrape complete: 0 sites succeeded; 0 failed; 0 positive-amount bonuses; 0 new records.
ok
test_concurrent_workers_can_insert_and_read_without_sqlite_api_errors (test_db_concurrency.SQLiteThreadSafetyTests.test_concurrent_workers_can_insert_and_read_without_sqlite_api_errors) ... ok
test_initialize_database_migrates_legacy_file (test_migration.UngolfMigrationTests.test_initialize_database_migrates_legacy_file) ... ok
test_migrate_renames_and_preserves_rows (test_migration.UngolfMigrationTests.test_migrate_renames_and_preserves_rows) ... ok
test_migration_is_idempotent (test_migration.UngolfMigrationTests.test_migration_is_idempotent) ... ok
test_offset_timestamps_are_normalized_to_utc (test_url_lifecycle.UrlLifecycleTests.test_offset_timestamps_are_normalized_to_utc) ... ok
test_requires_failed_attempts_spanning_full_72_hours (test_url_lifecycle.UrlLifecycleTests.test_requires_failed_attempts_spanning_full_72_hours) ... ok
test_skipped_url_is_not_counted_as_failure (test_url_lifecycle.UrlLifecycleTests.test_skipped_url_is_not_counted_as_failure) ... ok
test_success_resets_failure_window_and_recovers_quarantined_url (test_url_lifecycle.UrlLifecycleTests.test_success_resets_failure_window_and_recovers_quarantined_url) ... ok

----------------------------------------------------------------------
Ran 15 tests in 0.167s

OK
EXIT:0
```

## Acceptance criteria

### AC-1 Ungolfed names — PASS
Active Python (excluding `backup/` and the intentional legacy `ALTER TABLE t ADD COLUMN ec` inside migration) has no golfed table SQL. Canonical schema uses sites/bonuses/sessions/scrape_runs/logs.

```
=== AC-1 leftover golfed SQL (excl backup/tests/legacy ALTER) ===
NONE
```

### AC-2 Idempotent migration + MIGRATION.md — PASS
`migrate_ungolf_schema` runs on connect via `initialize_database` and via `python -m golf migrate`. Documented in MIGRATION.md. Unit tests seed an old-schema temp DB, migrate, and assert data intact + idempotency (`test_migrate_renames_and_preserves_rows`, `test_migration_is_idempotent`, `test_initialize_database_migrates_legacy_file`, `test_migrate_subcommand`).

```
=== AC-2 MIGRATION.md + migrate help ===
MIGRATION.md:present
# Schema migration: ungolf single-letter names

## Why
The SQLite schema historically used single-letter table and column names (`t`, `b`, `u`, `ec`, …).
Those identifiers are renamed to clear single-word names. Existing databases keep their data.

## How it runs
1. **Automatically** — `db.initialize_database()` calls `migrate_ungolf_schema()` before creating canonical tables, so any connect/init path applies renames first.
2. **CLI** — `python -m golf migrate` opens the configured DB and runs the same idempotent migration.

The migration is recorded in `schema_version` as `002_ungolf_schema` (after the historical `001_add_ec_column`).

## What it does
- Drops legacy FTS5 objects (`b_fts` / related triggers) before renames, then recreates `bonuses_fts` after columns are renamed.
- `ALTER TABLE … RENAME TO …` for tables:
  - `t` → `sites`
  - `b` → `bonuses`
  - `s` → `sessions`
  - `m` → `scrape_runs`
  - `l` → `logs`
usage: golf migrate [-h]

options:
  -h, --help  show this help message and exit
```

### AC-3 Primary CLI — PASS
`python -m golf` exposes run / scrape / interactive / export / migrate / pipeline. Legacy `main.py`, `run_scraper.py`, `run_fast.py` are thin shims; shell scripts are thin wrappers.

```
=== AC-3 CLI subcommands ===
usage: golf [-h] {run,scrape,interactive,export,migrate,pipeline} ...

Scrape sites, maintain history, build exports, migrate schema, and run the
dashboard.

positional arguments:
  {run,scrape,interactive,export,migrate,pipeline}
    run                 Full non-interactive scrape (alias of scrape).
    scrape              Full non-interactive scrape followed by
                        maintenance/exports.
    interactive         Dashboard + terminal UI.
    export              Regenerate analysis/viewer CSVs locally (no network
                        scrape).
    migrate             Apply idempotent schema renames to the SQLite DB.
    pipeline            Run maintenance and exports without scraping.

options:
  -h, --help            show this help message and exit
=== wrappers ===
==> main.py <==
"""Compatibility shim. Canonical entry point: python -m golf interactive"""
import sys
from golf.cli import main

==> run_scraper.py <==
"""Compatibility shim. Canonical entry point: python -m golf scrape"""
import sys
from golf.cli import main

==> run_fast.py <==
"""Deprecated compatibility shim; shared scraping logic lives in scrape_worker.py.

Use `python -m golf scrape --no-pipeline` for scrape-only operation.

==> device_run.sh <==
#!/bin/bash
# Canonical on-device entry point. Uses the project venv when present.
set -euo pipefail

==> scrape_and_deploy.sh <==
#!/bin/bash
# Thin wrapper around the canonical CLI scrape + optional legacy Anyclaw deploy.
set -euo pipefail

==> run.sh <==
#!/bin/bash
# Portable compatibility wrapper; use device_run.sh for all normal runs.
set -euo pipefail
```

### AC-4 Deduplicated scrape worker + export — PASS
Shared scrape logic lives in `scrape_worker.py` (`try_scrape`, `process_bonus`); CSV paths consolidated in `export_csv.py`; `build_exports.py` is a thin wrapper.

```
=== AC-4 modules ===
export_csv.py
golf/cli.py
scrape_worker.py
scraper.py:8:from scrape_worker import (
golf/cli.py:149:    from export_csv import build_analysis_exports, export_db_to_csv
build_exports.py:3:from export_csv import build_analysis_exports
```

### AC-5 Tests — PASS
15 tests OK including migration + network-free CLI smoke. See suite result above.

## Overall
All acceptance criteria PASS.
