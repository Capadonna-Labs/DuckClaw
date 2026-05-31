#!/usr/bin/env python3
"""
Idempotent migration: admin_console_users auth columns.

Spec: specs/features/platform/ADMIN_CONSOLE_AUTH.md
DuckDB uses JSON (not JSONB).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_MIGRATIONS = [
    "ALTER TABLE main.admin_console_users ADD COLUMN IF NOT EXISTS hash_algo TEXT DEFAULT 'pbkdf2_sha256'",
    "ALTER TABLE main.admin_console_users ADD COLUMN IF NOT EXISTS hash_params JSON",
    "ALTER TABLE main.admin_console_users ADD COLUMN IF NOT EXISTS failed_login_count INTEGER DEFAULT 0",
    "ALTER TABLE main.admin_console_users ADD COLUMN IF NOT EXISTS last_failed_at TIMESTAMP",
]


def apply_migration(con: object) -> None:
    for stmt in _MIGRATIONS:
        con.execute(stmt)  # type: ignore[attr-defined]


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply admin auth column migration")
    parser.add_argument("--db", help="Path to gateway DuckDB (default: get_gateway_db_path())")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo / "packages" / "shared" / "src"))

    db_path = (args.db or "").strip()
    if not db_path:
        from duckclaw.gateway_db import get_gateway_db_path

        db_path = (get_gateway_db_path() or "").strip()
    if not db_path:
        print("No DuckDB path", file=sys.stderr)
        return 1

    import duckdb

    con = duckdb.connect(db_path, read_only=False)
    try:
        apply_migration(con)
        print(f"Applied {len(_MIGRATIONS)} statements to {db_path}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
