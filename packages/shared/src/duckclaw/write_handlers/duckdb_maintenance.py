"""DuckDB maintenance typed write handlers."""
from __future__ import annotations

import re
from typing import Any


def _quote_duckdb_ident(value: str) -> str:
    ident = (value or "").strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", ident):
        raise ValueError(f"Invalid DuckDB identifier: {value}")
    return '"' + ident.replace('"', '""') + '"'


def _dedupe_lowered(values: Any) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in list(values or []):
        value = str(raw or "").strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _apply_drop_legacy_duckdb_objects(conn: Any, payload: dict) -> None:
    schemas = _dedupe_lowered(payload.get("schemas"))
    main_tables = _dedupe_lowered(payload.get("main_tables"))
    if not schemas and not main_tables:
        raise ValueError("No legacy DuckDB objects requested")

    existing_schemas = {
        str(row[0]).lower()
        for row in conn.execute("SELECT schema_name FROM information_schema.schemata").fetchall()
    }
    existing_main_tables = {
        str(row[0]).lower()
        for row in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
    }

    for table in main_tables:
        if table in existing_main_tables:
            conn.execute(f"DROP TABLE main.{_quote_duckdb_ident(table)}")

    for schema in schemas:
        if schema in existing_schemas:
            conn.execute(f"DROP SCHEMA {_quote_duckdb_ident(schema)} CASCADE")
