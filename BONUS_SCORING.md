# Bonus scoring and scraping workflow

## Score definitions

The exports retain the existing **Perceived Value** field and add two comparable weighted scores:

- `weighted_score_v1`: the original benefit-only formula, `(amount / effective_minwithdraw) * sqrt(maxwithdraw)`.
- `weighted_score` (shown as **Weighted v2** in the viewer): higher is better. It caps the credited bonus at the maximum payout, penalises a maximum payout below the minimum withdrawal threshold, and applies a rollover-multiplier penalty.
- `rollover_ratio_average`: the existing 60:40 burden metric, `0.60 * rollover + 0.40 * (effective_minwithdraw / amount)`. Lower is better. It is not a benefit score and is deliberately kept separate.

For v2, with amount A, effective minimum withdrawal M, maximum bonus payout X, and rollover multiplier r:

`min(A, X) / M * sqrt(X) * min(1, X / M) / (1 + 0.20 * r)`

The 0.20 penalty is a tunable starting point, not a calibrated probability or claim of expected profit.

## Missing data and confidence

- Effective minimum withdrawal: offer-specific value, then curated site-wide minimum, then default 50.
- Maximum payout: observed value, same-site median, dataset median, then configured fallback 3776.
- Rollover: observed value, same-site median, then dataset median. If there is no rollover evidence anywhere, v2 remains blank instead of pretending unknown means zero.
- `score_confidence`, `score_status`, `score_maxwithdraw_source`, and `score_rollover_source` disclose when estimates were used.
- High confidence means the required inputs were observed and no fallback was needed; medium means site-level estimates; low means global/default estimates or missing rollover.

The max-withdraw fallback of 3776 is a legacy configured estimate, not verified offer terms. It is explicitly labelled and should not be mistaken for observed data.

## Scrape and export

From the repository root, with the project's configured Python dependencies and credentials available:

1. `python main.py -r` starts the scraper in resume mode. The process loads URLs from `in/config/urls.txt`, selects configured accounts from the INI/environment, requests each site, authenticates, syncs bonus and promotion data, normalises fields, computes Perceived Value, fingerprints/deduplicates offers, and writes records to `data/base.db`. Runtime events are recorded in SQLite and best-effort in `data/events.jsonl`.
2. The scraper's completion callback invokes `publish_viewer.py` unless `auto_publish=false` in settings.
3. `publish_viewer.py` runs `export_viewer_data.py viewer/public`, which reads the database and writes:
   - `dayne-bonuses.csv`: raw-ish current bonus export plus score columns.
   - `dayne-bonuses-cleaned.csv`: positive-amount, deduplicated rows sorted by Perceived Value, with ratio retained.
   - `dayne-bonuses-fresh.csv`: legacy fresh snapshot (currently same source rows as raw).
   - `dayne-bonuses-all.csv`: all-time bonus detail and score columns.
   - `dayne-sites.csv`: per-site status and aggregate metrics.
4. Unless invoked with `--export-only`, the publisher stages only the five viewer CSVs, commits changed snapshots, and pushes the current branch. The viewer site rebuilds from the repository's configured GitHub Pages workflow.

Useful commands:

```bash
# Scrape/resume and automatically export/publish on completion
python main.py -r

# Rebuild CSVs locally without pushing
python publish_viewer.py --export-only

# Run the score regression tests
python -m unittest discover -s tests -v
```

For the separate analysis/export pipeline, run:

```bash
python build_exports.py
python clean_bonuses.py data/Dayne_Bonuses.csv
python compare_bonus_scores.py data/Dayne_Bonuses_Cleaned.csv
```

This produces an enriched `data/Dayne_Bonuses.csv`, a cleaned/ranked `data/Dayne_Bonuses_Cleaned.csv`, and a deduplicated rank comparison at `data/score_comparison.csv`. The analysis pipeline is distinct from the automatic viewer publisher above.

The scraper is long-running and interactive: its local dashboard is normally at `http://127.0.0.1:8000`. A scrape can fail at individual sites without invalidating all other records. Check the completion summary and `data/events.jsonl` for failures.

## Validation before promoting v2

Keep Perceived Value and v1 visible during the trial. Review top 25/50/100, inspect offers with low confidence, and compare deduplicated offer-level rankings. Do not treat correlation with Perceived Value as proof of correctness; the useful ground truth is real offer usability and actual withdrawal/wagering outcomes.
