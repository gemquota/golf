# I-ungolf-refactor: Ungolf schema names and consolidate entry points

**Status: completed.** The original refactor was implemented and subsequently consolidated with URL-lifecycle, artifact-audit, and repository-structure work in [PR #30](https://github.com/gemquota/golf/pull/30).

## Goal

Replace single-letter SQLite table/column names with clear single-word names, consolidate duplicate scrapers and entry points into one primary CLI, and keep existing SQLite data compatible through an idempotent migration.

## Acceptance criteria and outcome

- AC-1: Schema, SQL, and Python references use clear single-word table/column names. **Complete.**
- AC-2: Existing SQLite databases migrate idempotently using `ALTER TABLE ... RENAME`; migration is automatic on initialization and available through `python -m golf migrate`. Documented in `docs/migrations.md`. **Complete.**
- AC-3: One primary CLI exposes run/scrape/interactive/export/migrate/pipeline commands. Redundant compatibility entry points have been retired. **Complete.**
- AC-4: Shared scrape-worker logic and CSV export responsibilities have canonical owners. **Complete.**
- AC-5: Migration, CLI smoke, and regression tests cover the refactor. **Complete.**

## Scope delivered

- Root application modules, CLI and shell entry points.
- Tests and maintained documentation.
- Follow-on URL lifecycle, runtime artifact audit, and repository hygiene changes consolidated into PR #30.

## Historical boundary

The initial scope confirmation and migration decision remain recorded in `decisions.jsonl`. This file is a completion record, not a current backlog.
