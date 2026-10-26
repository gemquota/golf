#!/bin/bash
# Compatibility launcher. Canonical CLI: python3 golf.py interactive
set -e
cd "$(dirname "$0")"

echo "=== Stopping any previous canonical/legacy run ==="
pkill -f "python3.*(golf.py|main.py|run_scraper.py)" 2>/dev/null && sleep 2 || true

echo "=== Starting scraper and dashboard ==="
python3 -u golf.py interactive -r "$@"
