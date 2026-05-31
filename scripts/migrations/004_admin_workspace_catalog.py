#!/usr/bin/env python3
"""Idempotent migration: DB-first admin workspace and worker catalog."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


def _ensure_shared_src() -> None:
    repo = Path(__file__).resolve().parents[2]
    shared_src = repo / "packages" / "shared" / "src"
    if str(shared_src) not in sys.path:
        sys.path.insert(0, str(shared_src))


def apply_migration(con: Any) -> None:
    _ensure_shared_src()

    from duckclaw.admin_resources import ensure_admin_resource_tables
    from duckclaw.admin_worker_catalog import ensure_admin_worker_catalog_schema
    from duckclaw.admin_workspace import ensure_admin_workspace_schema

    ensure_admin_worker_catalog_schema(con)
    ensure_admin_workspace_schema(con)
    ensure_admin_resource_tables(con)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply admin workspace catalog migration")
    parser.add_argument("--db", help="Path to gateway DuckDB (default: get_gateway_db_path())")
    args = parser.parse_args()

    _ensure_shared_src()
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
        print(f"Applied admin workspace catalog migration to {db_path}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
