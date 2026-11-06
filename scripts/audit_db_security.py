#!/usr/bin/env python3
"""Inspect and optionally invalidate session data without printing secret values."""
from __future__ import annotations

import argparse
import configparser
import sqlite3
from pathlib import Path


SESSION_TABLES = ("sessions", "s")


def inspect_database(path: Path, scrub: bool = False) -> dict:
    if not path.exists():
        return {"exists": False, "session_rows": 0, "cookie_rows": 0, "session_data_rows": 0}
    connection = sqlite3.connect(str(path))
    try:
        names = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        table = next((name for name in SESSION_TABLES if name in names), None)
        if table is None:
            result = {"exists": True, "session_table": False, "session_rows": 0,
                      "cookie_rows": 0, "session_data_rows": 0}
            return result

        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        cookie_column = "cookies" if "cookies" in columns else "ck" if "ck" in columns else None
        data_column = "session_data" if "session_data" in columns else "data" if "data" in columns else None
        rows = connection.execute(f"SELECT * FROM {table}").fetchall()
        cookie_index = next((i for i, row in enumerate(connection.execute(
            f"PRAGMA table_info({table})"
        )) if row[1] == cookie_column), None) if cookie_column else None
        data_index = next((i for i, row in enumerate(connection.execute(
            f"PRAGMA table_info({table})"
        )) if row[1] == data_column), None) if data_column else None
        cookie_rows = sum(bool(row[cookie_index]) for row in rows) if cookie_index is not None else 0
        data_rows = sum(bool(row[data_index]) for row in rows) if data_index is not None else 0
        result = {
            "exists": True, "session_table": True, "session_rows": len(rows),
            "cookie_rows": cookie_rows, "session_data_rows": data_rows,
        }
        if scrub and rows:
            connection.execute(f"DELETE FROM {table}")
            connection.commit()
            connection.execute("VACUUM")
            result["scrubbed_rows"] = len(rows)
            result["remaining_rows"] = connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
        return result
    finally:
        connection.close()


def inspect_config(path: Path) -> dict:
    if not path.exists():
        return {"exists": False, "account_sections": 0, "populated_user_fields": 0,
                "populated_password_fields": 0}
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    sections = [name for name in parser.sections() if name.upper().startswith("U")]
    return {
        "exists": True,
        "account_sections": len(sections),
        "populated_user_fields": sum(bool(parser.get(name, "u", fallback="").strip()) for name in sections),
        "populated_password_fields": sum(bool(parser.get(name, "p", fallback="").strip()) for name in sections),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("databases", nargs="*", type=Path)
    parser.add_argument("--config", type=Path, action="append", default=[])
    parser.add_argument("--scrub-sessions", action="store_true",
                        help="Delete session rows in the supplied local audit copies.")
    args = parser.parse_args()

    for path in args.databases:
        result = inspect_database(path, scrub=args.scrub_sessions)
        print(f"database={path.name} " + " ".join(f"{key}={value}" for key, value in result.items()))
    for path in args.config:
        result = inspect_config(path)
        print(f"config={path.name} " + " ".join(f"{key}={value}" for key, value in result.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
