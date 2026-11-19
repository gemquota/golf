#!/usr/bin/env python3
"""Export registered site URLs grouped and sorted by platform merchant ID."""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

DEFAULT_OUTPUT = Path("data/sites_by_merchant.csv")


def _sort_key(value: str):
    """Sort integer-like IDs numerically, then textual IDs, then unidentified URLs."""
    if not value:
        return (2, 0, "")
    if value.isdecimal():
        return (0, int(value), value)
    return (1, 0, value.casefold())


def export_sites(db_path: str | Path | None = None,
                 output: str | Path = DEFAULT_OUTPUT) -> int:
    """Write one CSV row per merchant ID, retaining unidentified URLs separately."""
    if db_path is None:
        import db
        db_path = db.DB_PATH

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(sites)")
        }
        if "merchant_id" not in columns:
            raise RuntimeError(
                "merchant_id column is missing; run 'python -m golf migrate' first"
            )

        rows = conn.execute("""
            SELECT merchant_id, merchant_name, url, active, updated_at, error_code
            FROM sites
        """).fetchall()
    finally:
        conn.close()

    grouped = {}
    for row in rows:
        merchant_id = str(row["merchant_id"] or "").strip()
        url = str(row["url"] or "").strip()
        if not url:
            continue

        # An unidentified URL remains its own row. Never merge sites by name.
        key = ("merchant", merchant_id) if merchant_id else ("url", url)
        item = grouped.setdefault(key, {
            "merchant_id": merchant_id,
            "names": set(),
            "urls": set(),
            "active": set(),
            "updated_at": "",
            "errors": set(),
        })
        name = str(row["merchant_name"] or "").strip()
        if name:
            item["names"].add(name)
        item["urls"].add(url)
        if row["active"] is not None:
            item["active"].add(str(row["active"]))
        updated_at = str(row["updated_at"] or "")
        if updated_at > item["updated_at"]:
            item["updated_at"] = updated_at
        if row["error_code"] is not None:
            item["errors"].add(str(row["error_code"]))

    records = sorted(
        grouped.values(),
        key=lambda item: (
            _sort_key(item["merchant_id"]),
            min(item["urls"]).casefold(),
        ),
    )

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "merchant_id",
            "merchant_name",
            "urls",
            "url_count",
            "active_values",
            "last_updated",
            "error_codes",
        ])
        writer.writeheader()
        for item in records:
            writer.writerow({
                "merchant_id": item["merchant_id"],
                "merchant_name": " | ".join(sorted(item["names"], key=str.casefold)),
                "urls": " | ".join(sorted(item["urls"], key=str.casefold)),
                "url_count": len(item["urls"]),
                "active_values": " | ".join(sorted(item["active"])),
                "last_updated": item["updated_at"],
                "error_codes": " | ".join(sorted(item["errors"])),
            })

    identified = sum(bool(item["merchant_id"]) for item in records)
    print(
        f"Exported {len(records)} site records ({identified} identified, "
        f"{len(records) - identified} unidentified) to {output}"
    )
    return len(records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None, help="SQLite database path (defaults to GOLF_DB_PATH/data/base.db)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="CSV output path")
    args = parser.parse_args()
    export_sites(args.db, args.output)
