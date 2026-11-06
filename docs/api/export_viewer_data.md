# Viewer export API

`export_viewer_data.py` is a format adapter for the active Vite viewer. It reads canonical SQLite rows, delegates raw-payload normalization and score-context calculation to `export_csv.py`, and writes the viewer's public CSV snapshots.

## Output files

- `dayne-bonuses.csv`: raw current bonus records.
- `dayne-bonuses-cleaned.csv`: positive-amount, deduplicated, perceived-value-sorted records with the viewer ratio column.
- `dayne-bonuses-all.csv`: expanded historical/current record fields, including canonical score metadata.
- `dayne-sites.csv`: per-site activity and value rollups.

## Design boundary

The viewer exporter owns viewer column layouts and site-level aggregation. It does not own score formulas, score fallback policy, or dataset/site median calculation. Those belong to `bonus_scoring.py` and `export_csv.py`.

Run with `python export_viewer_data.py [output_dir]`.

See [export_viewer_data.py](../../export_viewer_data.py).
