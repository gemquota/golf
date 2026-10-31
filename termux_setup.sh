#!/bin/bash
# One-shot Termux setup for the Golf scraper.
# Usage: bash termux_setup.sh [github_url]
set -euo pipefail

REPO_URL="${1:-https://github.com/gemquota/golf.git}"
INSTALL_DIR="$HOME/golf"

echo "=== Installing Termux packages ==="
pkg update -y
pkg install -y python git binutils uv
# pandas/NumPy are native Termux packages; avoid building them from PyPI.
pkg install -y python-pandas
pkg install -y python-psutil || true

echo "=== Cloning/updating repository ==="
if [ -d "$INSTALL_DIR/.git" ]; then
    git -C "$INSTALL_DIR" pull --ff-only
elif [ ! -e "$INSTALL_DIR" ]; then
    git clone "$REPO_URL" "$INSTALL_DIR"
else
    echo "ERROR: $INSTALL_DIR exists but is not a Git repository." >&2
    exit 1
fi

cd "$INSTALL_DIR"
echo "=== Creating isolated uv environment ==="
uv venv --clear --system-site-packages
grep -Ev '^(pandas|psutil)([<=>~!].*)?$' requirements.txt > "$TMPDIR/golf-requirements.txt"
UV_LINK_MODE=copy uv pip install --python .venv/bin/python -r "$TMPDIR/golf-requirements.txt"

echo "=== Verifying native packages and application imports ==="
.venv/bin/python -c "import pandas; print('pandas', pandas.__version__)"
.venv/bin/python -c "import config, db, server, scraper, terminal; print('Golf modules OK')"

echo
echo "Setup complete. Start with:"
echo "  cd ~/golf && bash device_run.sh"
