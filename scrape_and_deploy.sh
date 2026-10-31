#!/bin/bash
# Legacy full scrape/export/deploy wrapper. Paths are resolved relative to this repo.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then PYTHON="$(command -v python3)"; fi

echo "=== Running canonical scraper + URL lifecycle maintenance ==="
"$PYTHON" -u run_scraper.py 2>&1 | tee "${TMPDIR:-/tmp}/golf_scrape_run.log"

# run_scraper.py already builds the current exports. Keep the optional cleaner.
if [ -f clean_bonuses.py ] && [ -f data/Dayne_Bonuses.csv ]; then
    echo "=== Cleaning CSV ==="
    "$PYTHON" clean_bonuses.py data/Dayne_Bonuses.csv
fi

# Preserve the historical Anyclaw deployment when the legacy viewer source is
# present. Newer checkouts without it still get the scrape and CSV exports.
VIEWER_DIR="$ROOT/dayne-bonuses-viewer"
if [ -d "$VIEWER_DIR" ] && [ -f "$VIEWER_DIR/package.json" ]; then
    echo "=== Building legacy viewer ==="
    cd "$VIEWER_DIR"
    npm run build
    cp app.json icon.svg dist/ 2>/dev/null || true
    if command -v zip >/dev/null 2>&1 && [ -d dist ]; then
        (cd dist && zip -qr ../dayne-bonuses.zip .)
    fi

    if [ -f dayne-bonuses.zip ] && command -v curl >/dev/null 2>&1; then
        echo "=== Deploying legacy viewer to Anyclaw ==="
        "$PYTHON" -c '
import base64, json
with open("dayne-bonuses.zip", "rb") as stream:
    encoded = base64.b64encode(stream.read()).decode()
print(json.dumps({"app_id":"dayne-bonuses","zip_b64":encoded,"app_type":"web_app","site_map":["/"]}))
' | curl --fail --silent --show-error -X POST https://anyclaw.store/api/deploy \
    -H "Content-Type: application/json" -d @- | "$PYTHON" -c '
import json, sys
data = json.load(sys.stdin)
print("Deployed:", data.get("claim_url", data))
'
    else
        echo "zip or curl unavailable; skipping Anyclaw deployment."
    fi
else
    echo "Legacy dayne-bonuses-viewer directory not present; skipping legacy web deployment."
fi

echo "=== Scrape, export and optional deployment complete ==="
