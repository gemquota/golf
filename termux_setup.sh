#!/bin/bash
# One-shot Termux setup for the golf bonus scraper.
# Usage: bash termux_setup.sh [github_url]
set -e

REPO_URL="${1:-https://github.com/gemquota/golf.git}"
INSTALL_DIR="$HOME/golf"
# /tmp is not writable inside Termux; $TMPDIR always is.
TMP_FILE="${TMPDIR:-$PREFIX/tmp}/req_no_pandas.txt"

echo "=== Installing packages ==="
pkg update -y
pkg install -y python git binutils
# pandas has no Android wheel on PyPI - install via Termux repo so pip skips it.
pkg install -y python-pandas || true
# psutil has no Android wheel either; terminal.py treats it as optional, but
# try the Termux build first for CPU/RAM stats.
pkg install -y python-psutil || true

echo "=== Cloning/updating repo ==="
if [ -d "$INSTALL_DIR/.git" ]; then
    git -C "$INSTALL_DIR" pull --ff-only || echo "pull failed, keeping local copy"
else
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

echo "=== Installing Python dependencies ==="
cd "$INSTALL_DIR"
# Skip pandas and psutil in pip (provided by Termux packages above, or optional).
grep -Ev '^(pandas|psutil)' requirements.txt > "$TMP_FILE"
pip install -r "$TMP_FILE"

echo "=== Smoke test ==="
python3 -c "import config, db, server, scraper, terminal; print('modules OK')"

echo ""
echo "Setup complete. Start scraping with:"
echo "  cd ~/golf && bash device_run.sh"
