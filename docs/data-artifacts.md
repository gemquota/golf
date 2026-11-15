# Runtime data artifacts

Run `python data_artifact_audit.py` to inspect the local `data/` directory.
Use `python data_artifact_audit.py --json` for machine-readable output. The
audit is read-only: it inventories files, hashes them, identifies exact
byte-for-byte duplicates, reports CSV/JSON/SQLite structure, and labels likely
runtime roles. It never deletes or rewrites anything.

## Canonical and derived data

- `data/base.db` is the canonical structured store for sites, bonuses,
  sessions, and scrape-run summaries.
- `data/account_state.json` is now the canonical URL registration state,
  including status, account ID, verification timestamps, and bounded transition
  history. `account_success.json` is retained as a read-only migration
  fallback and is no longer written by new scrapes.
- `data/site_state.json` is a runtime health projection with failure-window
  and quarantine history. It is not a byte-for-byte replacement for the
  latest row in SQLite's `sites` table.
- `data/accounts.csv` and viewer snapshots are derived exports. Rebuild them
  from canonical state rather than treating them as independent sources of
  truth.
- `data/bonus_history.csv` is a historical run/bonus ledger. Dated
  `bonuses_*.csv` files are run snapshots; they overlap in subject matter but
  are not automatically redundant because their retention and temporal
  semantics differ.

## Probe and diagnostic evidence

- `data/probe_attempts.csv` records each worker-level attempt, including
  account ID, retry number, outcome, error code, and exception type/message.
  It distinguishes application `E304` authentication rejection from actual
  HTTP 304 Not Modified (internal code `1304`).
- `data/site_errors.csv` remains a non-authentication error report.
- `data/bonus_reconciliation.csv` records per-site raw/eligible/inserted
  counts. It is not the same evidence as an HTTP probe.
- `data/events.jsonl`, CAPTCHA queues, raw responses, and parser diagnostics
  have separate operational or investigative uses. Consolidate them only
  after comparing event granularity, retention, and sensitive-data exposure.

## Safe cleanup guidance

- `tmp_*.csv` files are intermediate worker fragments. They are candidates
  for cleanup only after confirming no scrape is running and that the final
  timestamped export contains their rows.
- `ip_health.json` is a short-lived, reconstructible cache.
- Raw response and debug directories are optional diagnostics and may contain
  sensitive merchant/session material. Keep them local and apply a retention
  policy; do not publish or commit them.
- Exact hash matches are strong duplicate evidence. Similar names, identical
  headers, or overlapping columns are not enough to justify deletion.

The audit script deliberately reports candidates rather than deleting files.
Review its JSON output before changing retention or export ownership.
