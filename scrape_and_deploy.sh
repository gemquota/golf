#!/bin/bash
# Legacy full scrape/export/deploy wrapper. Paths are resolved relative to this repo.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then PYTHON="$(command -v python3)"; fi

echo "=== Running canonical scraper + URL lifecycle maintenance ==="
"$PYTHON" -u run_scraper.py 2>&1 | tee "${TMPDIR:-/tmp}/golf_scrape_run.log"

echo "=== Building exports ==="
"$PYTHON" build_exports.py
if [ -f clean_bonuses.py ]; then
    "$PYTHON" clean_bonuses.py data/Dayne_Bonuses.csv
fi

# The legacy Anyclaw package is optional. Only build it when its source exists.
VIEWER_DIR="$ROOT/dayne-bonuses-viewer"
if [ -d "$VIEWER_DIR" ] && [ -f "$VIEWER_DIR/package.json" ]; then
    echo "=== Building legacy viewer ==="
    cd "$VIEWER_DIR"
    npm run build
    if command -v zip >/dev/null 2>&1 && [ -d dist ]; then
        (cd dist && zip -qr ../dayne-bonuses.zip .)
    fi
else
    echo "Legacy dayne-bonuses-viewer directory not present; skipping legacy web bundle."
fi

echo "=== Scrape and export complete ==="
