# URL health and quarantine lifecycle

The scraper maintains the active URL list in `in/config/urls.txt` and a
quarantine list in `in/config/down.txt`. Runtime health history is stored in
`data/site_state.json` (local runtime data; it is not committed). Run-level
metrics are stored in SQLite's `scrape_runs` table, not a parallel CSV file.

## Removal rule

A URL is not marked failed merely because it was absent from a run. Only a
record in the SQLite `sites` table with a timestamp at or after the run's UTC
start marker is considered an attempt. This excludes URLs skipped by resume
mode, URLs not reached before a stop, and URLs omitted from a partial run.

The first recorded failed attempt starts a failure window. A later recorded
failed attempt must occur at least 72 hours after that first failure before
the URL is moved from `urls.txt` to `down.txt`. A successful scrape resets
the failure window and its failure count. This conservative two-observation
rule prevents a single outage or an unattended three-day gap from being
mistaken for three days of confirmed failure.

All run markers and SQLite `CURRENT_TIMESTAMP` comparisons use UTC. The
health processor is idempotent for the same per-URL attempt timestamp.

## Account selection

All configured accounts are authorised for the URL family in `in/config/urls.txt`. Each run uses this ordered schedule:

1. Randomize the full eligible URL list and attempt every URL with the primary account (`U1`).
2. In account order (`U2`, `U3`, ...), retry URLs with a previously verified association to that account. Skip URLs already successful during the U1 pass.
3. After all known-account batches finish, run fallback passes in account order (`U2`, `U3`, ...). Each pass includes only URLs whose latest result is the explicit authentication rejection `E304`, and skips any URL/account pair already attempted during this run.
4. Stop trying a URL after a successful scrape or when all configured accounts have been exhausted.

Each batch is randomized, but account-pass order is stable. The worker's bounded retries remain on the same URL/account pair. A successful scrape immediately persists the verified URL/account association for later runs.

Only `E304` is treated as a conclusive authentication rejection for fallback. Timeouts, network failures, server errors, HTTP errors and CAPTCHA responses are inconclusive and do not trigger credential rotation. URLs that receive only conclusive authentication rejections across all attempted accounts are recorded as unregistered; mixed or transient outcomes remain unknown.

## Error reports and CAPTCHA review

Every final failed URL/account attempt with a non-authentication error is appended
to `data/site_errors.csv`. The report includes the timestamp, URL, account ID,
numeric error code, category and exception message. Authentication rejection
(`E304`) is deliberately excluded because it is handled by account discovery.

CAPTCHA failures (`E202`) are also added to `data/captcha_required.txt`, a
deduplicated manual-review queue. The queue persists across runs. Open the file
to review the affected sites, then remove each URL after manually checking it.
If that URL triggers another CAPTCHA later, it is added to the queue again.
A successful scrape does not silently erase an outstanding manual-review item.

Both files are created under `data/` on the first applicable failure. They are
local runtime reports and should not be committed if they contain private site
or account information.

## Recovery

To retry a quarantined URL, add it back to `in/config/urls.txt`. A successful
scrape changes its state to `up`, clears the failure window, and removes it
from `down.txt`. A failed retry retains the existing failure history and can
be quarantined again.

## Entry points

- `bash device_run.sh`: recommended Termux dashboard entry point; prefers
  `.venv/bin/python`.
- `bash run.sh`: portable compatibility wrapper around `device_run.sh`.
- `python run_scraper.py`: standalone CLI run with maintenance and exports.
- `python run_fast.py`: single-account fast mode, also followed by maintenance.

Each completed entry point calls the same `maintain_pipeline.run_pipeline()`
function. A crashed or interrupted run does not synthesize failures for URLs
that were never attempted.

## Tests

Run regression tests with:

```sh
python -m unittest discover -s tests -v
```

GitHub Actions runs the test suite and compiles the Python modules on pushes
and pull requests.
