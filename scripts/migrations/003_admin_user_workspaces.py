#!/usr/bin/env python3
"""Idempotent migration: admin user profiles and runtime agents."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_MIGRATIONS = [
    """
    CREATE TABLE IF NOT EXISTS main.admin_user_profiles (
        email VARCHAR PRIMARY KEY,
        tenant_id VARCHAR NOT NULL UNIQUE,
        telegram_user_id VARCHAR,
        channels_json TEXT,
        default_worker_id VARCHAR DEFAULT 'default',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS main.admin_user_agents (
        tenant_id VARCHAR NOT NULL,
        owner_email VARCHAR NOT NULL,
        worker_id VARCHAR NOT NULL,
        display_name VARCHAR NOT NULL,
        source_template_id VARCHAR DEFAULT 'default',
        manifest_path VARCHAR NOT NULL,
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (tenant_id, worker_id)
    )
    """,
]


def apply_migration(con: object) -> None:
    for stmt in _MIGRATIONS:
        con.execute(stmt)  # type: ignore[attr-defined]


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply admin user workspace migration")
    parser.add_argument("--db", help="Path to gateway DuckDB (default: get_gateway_db_path())")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[2]
    shared_src = repo / "packages" / "shared" / "src"
    if str(shared_src) not in sys.path:
        sys.path.insert(0, str(shared_src))

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
