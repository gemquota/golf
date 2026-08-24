#!/bin/bash
# Run the scraper on-device and let the completion hook publish fresh
# viewer CSVs to GitHub (which triggers the Pages deploy).
#
# First time only: authenticate git push once, e.g.:
#   gh auth login          (after: pkg install gh)
#   # or: git credential-store with a fine-grained token you generate yourself
#
# Usage: bash device_run.sh [-s]
#   -s  shuffle URL order instead of sorting by historical yield
set -e
cd "$(dirname "$0")"

echo "=== Stopping any previous run ==="
pkill -f "python3.*main.py" 2>/dev/null && sleep 2 || true

ARGS="-r"   # resume: skip URLs that succeeded in the last 24h
[ "$1" = "-s" ] && ARGS="$ARGS -s"

echo "=== Starting scraper (dashboard: http://localhost:8000) ==="
# On scrape completion, main.py auto-runs publish_viewer.py, which exports
# all 5 viewer CSVs and pushes them -> Pages rebuilds automatically.
python3 -u main.py $ARGS
