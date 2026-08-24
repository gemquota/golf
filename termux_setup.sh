#!/bin/bash
# One-shot Termux setup for the golf bonus scraper.
# Usage: bash termux_setup.sh [github_url]
set -e

REPO_URL="${1:-https://github.com/gemquota/golf.git}"
INSTALL_DIR="$HOME/golf"

echo "=== Installing packages ==="
pkg update -y
pkg install -y python git binutils
# pandas has no Android wheel on PyPI - install via Termux repo so pip skips it.
pkg install -y python-pandas || true

echo "=== Cloning/updating repo ==="
if [ -d "$INSTALL_DIR/.git" ]; then
    git -C "$INSTALL_DIR" pull --ff-only || echo "pull failed, keeping local copy"
else
    git clone "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

echo "=== Installing Python dependencies ==="
# Skip pandas in pip (already provided by python-pandas above).
grep -v '^pandas' requirements.txt > /tmp/req_no_pandas.txt
pip install -r /tmp/req_no_pandas.txt

echo "=== Smoke test ==="
cd "$INSTALL_DIR"
python3 -c "import config, db, server, scraper, terminal; print('modules OK')"

echo ""
echo "Setup complete. Start scraping with:"
echo "  cd ~/golf && bash device_run.sh"
