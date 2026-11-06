#!/bin/bash
# Thin wrapper around the canonical CLI scrape + optional legacy Anyclaw deploy.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then PYTHON="$(command -v python3)"; fi

echo "=== Running canonical scraper + URL lifecycle maintenance ==="
"$PYTHON" -u -m golf scrape --no-publish 2>&1 | tee "${TMPDIR:-/tmp}/golf_scrape_run.log"

if [ -f clean_bonuses.py ] && [ -f data/Dayne_Bonuses.csv ]; then
    echo "=== Cleaning CSV ==="
    "$PYTHON" clean_bonuses.py data/Dayne_Bonuses.csv
fi

echo "Scrape complete. Use publish_viewer.py for the active Vite viewer."
