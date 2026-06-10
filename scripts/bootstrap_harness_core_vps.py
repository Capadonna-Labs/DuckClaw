#!/usr/bin/env python3
"""Idempotent harness_core DDL on hub DuckDB (VPS one-shot)."""
from __future__ import annotations

import os
import sys

import duckdb

DDL = """
CREATE SCHEMA IF NOT EXISTS harness_core;
CREATE TABLE IF NOT EXISTS harness_core.homeostasis_targets (
    tenant_id VARCHAR PRIMARY KEY,
    targets_json JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS harness_core.meditate_runs (
    run_id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    distance_vector JSON,
    actions_json JSON,
    status VARCHAR NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def main() -> int:
    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else (os.environ.get("DUCKCLAW_FINANZ_DB_PATH") or "").strip()
    )
    if not path:
        print("usage: bootstrap_harness_core_vps.py <duckdb_path>", file=sys.stderr)
        return 1
    con = duckdb.connect(path, read_only=False)
    try:
        for stmt in DDL.strip().split(";"):
            s = stmt.strip()
            if s:
                con.execute(s)
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'harness_core' ORDER BY 1"
        ).fetchall()
        print("ok", path)
        print("tables:", [r[0] for r in rows])
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
