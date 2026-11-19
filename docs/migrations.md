# Schema migration: ungolf single-letter names

## Why
The SQLite schema historically used single-letter table and column names (`t`, `b`, `u`, `ec`, …).
Those identifiers are renamed to clear single-word names. Existing databases keep their data.

## How it runs
1. **Automatically** — `db.initialize_database()` calls `migrate_ungolf_schema()` before creating canonical tables, so any connect/init path applies renames first.
2. **CLI** — `python -m golf migrate` opens the configured DB and runs the same idempotent migration.

The schema history includes `001_add_ec_column`, `002_ungolf_schema`, and `003_site_merchant_id`.

## What it does
- Drops legacy FTS5 objects (`b_fts` / related triggers) before renames, then recreates `bonuses_fts` after columns are renamed.
- `ALTER TABLE … RENAME TO …` for tables:
  - `t` → `sites`
  - `b` → `bonuses`
  - `s` → `sessions`
  - `m` → `scrape_runs`
  - `l` → `logs`
- `ALTER TABLE … RENAME COLUMN …` for abbreviated columns on each table (see name map below).
- Safe to re-run: skips renames when the new name already exists.

## Name map

| Old | New |
|-----|-----|
| **Tables** | |
| t | sites |
| b | bonuses |
| s | sessions |
| m | scrape_runs |
| l | logs |
| **sites columns** | |
| u | url |
| m | merchant_name |
| p | referral_url |
| g | short_url |
| a | active |
| ts | updated_at |
| ec | error_code |
| **bonuses columns** | |
| uid | bonus_uid |
| eid | external_id |
| u | url |
| v | amount |
| pv | perceived_value |
| w | wager |
| c | claim |
| t | kind |
| raw | raw_json |
| h | content_hash |
| exp | expiry |
| fp | fingerprint |
| s1 | first_seen |
| sl | last_seen |
| mname | merchant_name |
| **sessions columns** | |
| uid | user_id |
| u | url |
| ck | cookies |
| data | session_data |
| ua | user_agent |
| ts | updated_at |
| **scrape_runs columns** | |
| rid | run_id |
| ts | created_at |
| dur | duration |
| cnt | count |
| new | new_count |
| spv | sum_perceived_value |
| err | error_count |
| **logs columns** | |
| ts | created_at |
| lvl | level |
| src | source |
| msg | message |

## Merchant IDs and site exports

Migration `003_site_merchant_id` adds `sites.merchant_id`. Successful scrapes persist the platform merchant ID alongside the merchant name for the URL being scraped. Existing rows remain NULL until those URLs are successfully scraped again; IDs are never inferred from bonus `external_id` values or merchant names.

Generate `data/sites_by_merchant.csv` with:

```sh
python export_sites.py
```

The export groups registered URLs by merchant ID, sorts numeric IDs numerically, and keeps URLs without an ID as separate unidentified rows. It deliberately exports all URLs in one `urls` field because the current schema does not identify a canonical URL among mirrors.

## Operator notes
- Do not hand-edit a live DB while a scrape is running.
- Backup `data/base.db` before the first migrate on a production device if you want a rollback copy.
- Fresh installs create the canonical schema directly; the migration is a no-op when only new names exist.
