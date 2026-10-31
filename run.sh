#!/bin/bash
# Portable compatibility wrapper; use device_run.sh for all normal runs.
set -euo pipefail
cd "$(dirname "$0")"
exec bash ./device_run.sh "${@}"
