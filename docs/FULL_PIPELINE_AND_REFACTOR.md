# Full scraping process and refactor roadmap

## Canonical entry point

Use `python golf.py` for new runs:

- `python golf.py interactive -r`: dashboard/terminal UI plus post-scrape pipeline.
- `python golf.py scrape -r`: full non-interactive scrape and post-processing.
- `python golf.py scrape --no-pipeline`: scrape and persist only.
- `python golf.py pipeline --no-publish`: maintenance and local exports.
- `python golf.py export`: regenerate viewer CSVs without publishing.
- `python golf.py publish`: regenerate and push viewer CSVs.

The old `main.py`, `run_scraper.py`, and `run_fast.py` are compatibility shims. The duplicated fast worker has been removed in favour of `scraper.py`.

## Full scraping process

1. **Config load:** `in/config/config.ini` (legacy `in/config.ini` also read), `GOLF_*` environment overrides, `in/config/urls.txt`, optional `in/config/proxies.txt`, account sections, delays, worker count and optional API keys.
2. **Initialisation:** create `data/`; call `db.initialize_database()` for schema/migrations and SQLite WAL.
3. **IP check:** optional AbuseIPDB check when a key is configured; reputation result is cached for an hour by the network layer.
4. **Account assignment:** URLs in `data/account_success.json` use their known successful account only. Unknown URLs try accounts sequentially until `ec=200`. Authentication rejection is distinguished from inconclusive network/HTTP/CAPTCHA failures.
5. **Concurrent worker pool:** `ThreadPoolExecutor` uses the configured worker count. Each worker waits a random MIN/MAX delay; calls `get_page`; extracts merchant ID/name; loads an SQLite session if younger than six hours or logs in; calls `syncData`; retries login/sync once if needed; optionally dumps raw JSON; combines bonus and promotion arrays; normalises records; skips non-positive amounts; calculates Perceived Value, expiry and fingerprint; fuzzy-matches existing bonuses; writes structured fields plus raw JSON to SQLite; tracks mirrors; and appends a per-worker temporary CSV row.
6. **Status/logging:** worker completion updates site success/error code and logs to SQLite `l` plus best-effort `data/events.jsonl`. The shared SQLite connection is protected by an `RLock`; preserve this when changing concurrency.
7. **Merge:** worker temp CSVs are merged into timestamped `data/bonuses_YYYYMMDD_HHMMSS.csv`, then temp chunks are removed.
8. **Maintenance:** `maintain_pipeline.py` updates `site_state.json`, moves URLs failed for over three days to `down.txt`, writes `accounts.csv`, appends `bonus_history.csv`, and appends `scrape_runs.csv`.
9. **Analysis exports:** `build_exports.py` writes `Dayne_Bonuses_Raw.csv` (expanded source JSON) and enriched `Dayne_Bonuses.csv`. `clean_bonuses.py` filters amount>0, applies the ratio ceiling, deduplicates by URL/name/amount and writes `Dayne_Bonuses_Cleaned.csv`. `compare_bonus_scores.py` writes `score_comparison.csv`.
10. **Viewer exports:** `export_viewer_data.py` writes `viewer/public/dayne-bonuses.csv`, `dayne-bonuses-cleaned.csv`, `dayne-bonuses-fresh.csv`, `dayne-bonuses-all.csv`, and `dayne-sites.csv`.
11. **Publish:** `publish_viewer.py` stages only viewer CSVs, commits changed snapshots and pushes the current branch; the configured Pages workflow rebuilds the viewer.

Analysis exports and viewer exports have different consumers. Keep both until their schemas are deliberately consolidated and tested.

## Database naming migration

Current legacy table names and target names:

| Legacy | Canonical |
|---|---|
| `t` | `sites` |
| `b` | `bonuses` |
| `s` | `sessions` |
| `m` | `scrape_runs` |
| `l` | `logs` |

Representative column renames: `u`→`url`, `ec`→`error_code`, `uid`→`bonus_uid`, `eid`→`external_id`, `v`→`amount`, `pv`→`perceived_value`, `raw`→`raw_json`, `fp`→`fingerprint`, `exp`→`expiry`, `s1`→`first_seen`, `sl`→`last_seen`, `mname`→`merchant_name`, `ts`→`updated_at`.

**Do not rename tables in place while legacy queries remain.** The migration needs a backup, a versioned transaction, canonical schema, compatibility views/triggers during transition, rebuilt FTS5 indexes/triggers, and tests for row counts, IDs, search, writes and rollback. The schema rename is not yet implemented in this CLI branch.

## Refactor stages

1. Consolidate CLI entry points (started here).
2. Extract the shared session/sync/normalise/persist core from `scraper.py`; add fixture-based tests.
3. Make analysis and viewer exporters consume one shared record layer while retaining their distinct output schemas.
4. Migrate database tables/columns with compatibility aliases; remove aliases only after repository-wide search and tests.
5. Remove obsolete shell duplication after tests cover account discovery, migrations, CSV schemas, and idempotent publishing.

Do not test a schema migration against the live database. Use a backup copy first.
