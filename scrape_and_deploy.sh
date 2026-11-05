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

VIEWER_DIR="$ROOT/dayne-bonuses-viewer"
if [ -d "$VIEWER_DIR" ] && [ -f "$VIEWER_DIR/package.json" ]; then
    echo "=== Building legacy viewer ==="
    cd "$VIEWER_DIR"
    npm run build
    cp app.json icon.svg dist/ 2>/dev/null || true
    if command -v zip >/dev/null 2>&1 && [ -d dist ]; then
        (cd dist && zip -qr ../dayne-bonuses.zip .)
    fi
    echo "Legacy viewer build complete (deploy step left to operator)."
else
    echo "No legacy dayne-bonuses-viewer directory; scrape/export only."
fi
