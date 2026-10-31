#!/bin/bash
# Canonical on-device entry point. Uses the project venv when present.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="$PWD/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    PYTHON="$(command -v python3)"
fi

echo "=== Stopping any previous Golf dashboard run ==="
if command -v pkill >/dev/null 2>&1; then
    pkill -f "[p]ython.*main.py" 2>/dev/null || true
fi

ARGS=(-r)
if [ "${1:-}" = "-s" ]; then
    ARGS+=(-s)
fi

echo "=== Starting Golf (dashboard: http://localhost:8000) ==="
exec "$PYTHON" -u main.py "${ARGS[@]}"
