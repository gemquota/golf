# URL health and quarantine lifecycle

The scraper maintains the active URL list in `in/config/urls.txt` and a
quarantine list in `in/config/down.txt`. Runtime health history is stored in
`data/site_state.json` (local runtime data; it is not committed).

## Removal rule

A URL is not marked failed merely because it was absent from a run. Only a
record in the SQLite `t` table with a timestamp at or after the run's UTC
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
