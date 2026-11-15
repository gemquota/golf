#!/usr/bin/env python3
"""Read-only inventory and redundancy audit for Golf's runtime data directory.

The audit never deletes, rewrites, or moves files. It reports exact duplicates,
file schemas, SQLite tables, stale worker fragments, and likely derived outputs.
"""
import argparse
import csv
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify(path):
    name = path.name.lower()
    rel = path.as_posix().lower()
    if name == "base.db" or name.endswith((".db-wal", ".db-shm")):
        return "canonical_store" if name == "base.db" else "database_sidecar"
    if re.fullmatch(r"tmp_.*\.csv", name):
        return "ephemeral_worker_fragment"
    if name in {"ip_health.json"}:
        return "expiring_cache"
    if name in {"account_success.json"}:
        return "legacy_duplicate_projection"
    if name in {"account_state.json", "site_state.json"}:
        return "runtime_state_projection"
    if name in {"accounts.csv", "registered_accounts.csv", "failed_attempts.csv",
                "bonus_history.csv", "bonus_reconciliation.csv", "probe_attempts.csv",
                "site_errors.csv", "events.jsonl", "captcha_required.txt"}:
        return "operational_ledger_or_queue"
    if "raw_responses" in rel or "/debug/" in rel:
        return "optional_diagnostic"
    if re.fullmatch(r"bonuses?_.*\.csv", name):
        return "dated_scrape_snapshot"
    if name in {"dayne_bonuses.csv", "dayne_bonuses_cleaned.csv",
                "dayne_bonuses_enriched.csv", "extracted_bonuses.csv"}:
        return "derived_export"
    return "unclassified"


def inspect_file(path):
    item = {
        "path": path.as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "role": classify(path),
    }
    suffix = path.suffix.lower()
    if suffix == ".csv":
        try:
            with path.open("r", newline="", encoding="utf-8-sig") as stream:
                reader = csv.reader(stream)
                header = next(reader, [])
                rows = sum(1 for _ in reader)
            item.update({"format": "csv", "columns": header, "row_count": rows})
        except (OSError, UnicodeError, csv.Error) as exc:
            item["read_error"] = str(exc)
    elif suffix == ".json":
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            item["format"] = "json"
            item["top_level_type"] = type(value).__name__
            if isinstance(value, dict):
                item["top_level_keys"] = sorted(value.keys())[:100]
        except (OSError, UnicodeError, ValueError) as exc:
            item["read_error"] = str(exc)
    elif suffix in {".jsonl", ".txt"}:
        item["format"] = "jsonl" if suffix == ".jsonl" else "text"
        try:
            with path.open("r", encoding="utf-8") as stream:
                item["line_count"] = sum(1 for _ in stream)
        except (OSError, UnicodeError) as exc:
            item["read_error"] = str(exc)
    elif suffix == ".db":
        item["format"] = "sqlite"
        try:
            conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
            tables = [row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )]
            item["tables"] = {}
            for table in tables:
                quoted = '"' + table.replace('"', '""') + '"'
                item["tables"][table] = conn.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
            conn.close()
        except sqlite3.Error as exc:
            item["read_error"] = str(exc)
    return item


def audit(root):
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(f"Data directory does not exist: {root}")
    files = sorted(path for path in root.rglob("*") if path.is_file())
    inspected = [inspect_file(path) for path in files]
    by_hash = defaultdict(list)
    for item in inspected:
        by_hash[item["sha256"]].append(item["path"])
    exact_duplicates = [
        {"sha256": digest, "paths": paths}
        for digest, paths in sorted(by_hash.items()) if len(paths) > 1
    ]
    candidates = []
    for item in inspected:
        if item["role"] == "legacy_duplicate_projection":
            candidates.append({
                "path": item["path"],
                "assessment": "High-confidence redundancy candidate",
                "reason": "account_state.json now carries status and account_id; this legacy URL-to-account map is read only as a migration fallback.",
                "action": "Keep during migration; remove only after confirming every consumer reads account_state.json.",
            })
        elif item["role"] == "ephemeral_worker_fragment":
            candidates.append({
                "path": item["path"],
                "assessment": "Conditional redundancy",
                "reason": "Worker fragments are intermediate inputs to the merged run export.",
                "action": "Remove only after confirming no scrape is active and the merged export contains their rows.",
            })
        elif item["role"] == "expiring_cache":
            candidates.append({
                "path": item["path"],
                "assessment": "Disposable cache",
                "reason": "Reconstructible IP reputation cache with a short validity window.",
                "action": "Safe to regenerate; retain only if avoiding an extra lookup is useful.",
            })
        elif item["role"] == "derived_export":
            candidates.append({
                "path": item["path"],
                "assessment": "Possible derived-output overlap",
                "reason": "Generated exports may overlap canonical SQLite data or other export stages.",
                "action": "Compare consumers, schema, and row identity before consolidating; do not delete based on filename.",
            })
    return {
        "root": str(root),
        "file_count": len(inspected),
        "total_bytes": sum(item["bytes"] for item in inspected),
        "files": inspected,
        "exact_duplicates": exact_duplicates,
        "redundancy_candidates": candidates,
        "notes": [
            "Matching CSV headers do not prove duplicate content.",
            "Dated scrape snapshots and bonus_history.csv serve different temporal purposes.",
            "site_state.json preserves a failure window and quarantine history not represented by the latest sites row alone.",
            "bonus_reconciliation.csv, site_errors.csv, and probe_attempts.csv are different evidence streams; merge only after proving their event granularity and retention requirements.",
            "This command is read-only and never deletes artifacts.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data", help="Runtime data directory (default: data)")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()
    result = audit(args.data_dir)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print(f"Data artifact audit: {result['root']}")
    print(f"{result['file_count']} files, {result['total_bytes']:,} bytes")
    for item in result["files"]:
        print(f"{item['role']:30} {item['bytes']:>10,}  {item['path']}")
    if result["exact_duplicates"]:
        print("\nExact duplicates:")
        for group in result["exact_duplicates"]:
            print("  " + " = ".join(group["paths"]))
    print("\nRedundancy candidates:")
    for item in result["redundancy_candidates"]:
        print(f"  {item['assessment']}: {item['path']}")
        print(f"    {item['reason']}")
        print(f"    Action: {item['action']}")
    print("\nNo files were changed.")


if __name__ == "__main__":
    main()
