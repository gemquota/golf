#!/usr/bin/env python3
"""Export fresh viewer CSVs and publish them to the golf repo's viewer/.

Runs export_viewer_data.py against the current DB snapshot, then stages,
commits and pushes any changed CSVs under viewer/public/. Safe to run
repeatedly - exits quietly when there is nothing new.

Usage: python3 publish_viewer.py [--export-only]
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VIEWER_PUBLIC = ROOT / "viewer" / "public"

CSV_FILES = [
    "dayne-bonuses.csv",
    "dayne-bonuses-cleaned.csv",
    "dayne-bonuses-fresh.csv",
    "dayne-bonuses-all.csv",
    "dayne-sites.csv",
]


def run(cmd):
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(cmd)} failed ({result.returncode}): {result.stderr.strip()[:400]}"
        )
    return result


def export():
    run([sys.executable, str(ROOT / "export_viewer_data.py"), str(VIEWER_PUBLIC)])


def publish():
    csv_paths = [f"viewer/public/{name}" for name in CSV_FILES if (VIEWER_PUBLIC / name).exists()]
    if not csv_paths:
        print("publish_viewer: no CSVs found, skipping")
        return False
    run(["git", "add", *csv_paths])
    status = run(["git", "status", "--porcelain", "--cached", "--", "viewer/public"])
    if not status.stdout.strip():
        print("publish_viewer: no changes to publish")
        return False
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    run(["git", "commit", "-m", f"Refresh viewer data snapshot ({stamp})"])
    run(["git", "push", "origin", "HEAD"])
    print("publish_viewer: pushed refreshed viewer data")
    return True


def main(export_only=False):
    export()
    if not export_only:
        publish()


if __name__ == "__main__":
    main(export_only="--export-only" in sys.argv)
