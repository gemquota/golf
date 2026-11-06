# Canonical CSV export API

`export_csv.py` is the shared transformation layer for database-backed CSV exports.

## Shared helpers

- `num(value)`: parse finite numeric values.
- `domain(url)`: normalize a URL to its hostname.
- `normalize_bonus_json(raw_json)`: safely decode raw payloads and lowercase keys.
- `build_scoring_context(rows)`: calculate per-site and dataset medians once for a complete export.
- `score_bonus_row(row, normalized, mins, context)`: apply the canonical scoring policy to one record.
- `site_minimums(out_dir)`: load configured site withdrawal minimums.

## Export functions

- `fetch_bonus_rows(db_path)`: load canonical bonus records.
- `write_raw(rows, out_dir)`: write the raw archival export.
- `write_enriched(rows, mins, out_dir)`: write the scored analysis export.
- `write_dayne_simple(rows, out_path)`: write the flat compatibility CSV.
- `build_analysis_exports(db_path, out_dir)`: produce raw and enriched analysis files.
- `export_db_to_csv(db_path, out_path)`: produce the flat CSV.

This module is the source of truth for normalization and score-context construction. Viewer-specific serializers should consume these helpers rather than reimplementing them.

See [export_csv.py](../../export_csv.py) and [bonus_scoring.py](../../bonus_scoring.py).
