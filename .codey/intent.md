# I-ungolf-refactor: Ungolf schema names and consolidate entry points

## Goal
Replace single-letter SQLite table/column names with clear single-word names, consolidate duplicate scrapers and entry points into one primary CLI, and keep existing SQLite data compatible via an idempotent migration.

## Acceptance Criteria
- AC-1: Schema, SQL, and Python references use clear single-word table/column names (no single-letter golfed identifiers for tables t/b/s/m/l or their abbreviated columns).
- AC-2: An idempotent migration renames tables/columns in existing SQLite DBs (ALTER TABLE ... RENAME), runs automatically on connect or via a CLI migrate command, and is documented in MIGRATION.md.
- AC-3: One primary CLI exposes subcommands including run/scrape/interactive/export/migrate; former entry points are thin wrappers or removed; shell scripts are thin wrappers or removed.
- AC-4: Shared scrape worker / try_scrape / process_bonus logic lives in one module used by all scrape entry points; CSV export paths are deduplicated into one export module where practical.
- AC-5: Existing unit tests pass; new migration tests (old-schema temp DB → migrate → data intact) and network-free CLI smoke tests for each subcommand pass.

## Scope
- Repository root Python modules, shell entry scripts, tests, docs (MIGRATION.md), and .codey control plane.
- No dependency changes beyond essentials.
- Do not commit DB data files, scraped/gambling/BIE data, secrets, or gitignored credential files.

## Out of Scope
- Changing viewer frontend behaviour beyond consuming renamed DB fields via exporters.
- Deleting or rewriting git history.
- Merging the PR.
