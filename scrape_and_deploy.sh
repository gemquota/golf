#!/bin/bash
# Canonical non-interactive scrape + maintenance + exports + viewer publish.
set -euo pipefail
cd "$(dirname "$0")"

LOG_FILE="${GOLF_LOG_FILE:-/tmp/golf-scrape.log}"
echo "=== Starting full Golf pipeline ==="
echo "Log: $LOG_FILE"
python3 -u golf.py scrape -r "$@" 2>&1 | tee "$LOG_FILE"
echo "=== Full pipeline finished ==="
