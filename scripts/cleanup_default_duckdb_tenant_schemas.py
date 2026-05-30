#!/usr/bin/env python3
"""
Elimina esquemas/tablas tenant-specific de archivos default.duckdb.

Conserva tablas core en ``main``: agent_config, authorized_users, task_audit_log,
user_shared_db_access.

Uso:
  python scripts/cleanup_default_duckdb_tenant_schemas.py --inspect
  python scripts/cleanup_default_duckdb_tenant_schemas.py --path db/private/1726618406/default.duckdb --apply
  python scripts/cleanup_default_duckdb_tenant_schemas.py --all-defaults --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import duckdb

# Esquemas de dominio (no pertenecen al tenant default genérico).
TENANT_EXTRA_SCHEMAS: tuple[str, ...] = (
    "leila",
    "pqrsd",
    "pqrsd_crm",
    "quant",
    "quant_core",
    "war_room",
    "war_room_core",
)

# Tablas en main creadas por workers/domains específicos.
TENANT_EXTRA_MAIN_TABLES: tuple[str, ...] = (
    "leila_orders",
    "leila_products",
)

CORE_MAIN_TABLES: frozenset[str] = frozenset(
    {
        "agent_config",
        "authorized_users",
        "task_audit_log",
        "user_shared_db_access",
    }
)


def _list_schemas(conn: duckdb.DuckDBPyConnection) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT schema_name
        FROM information_schema.schemata
        WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'main')
        ORDER BY 1
        """
    ).fetchall()
    return [str(r[0]) for r in rows]


def _list_main_tables(conn: duckdb.DuckDBPyConnection) -> list[str]:
    rows = conn.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'main'
        ORDER BY 1
        """
    ).fetchall()
    return [str(r[0]) for r in rows]


def _plan_cleanup(conn: duckdb.DuckDBPyConnection) -> tuple[list[str], list[str]]:
    schemas = _list_schemas(conn)
    drop_schemas = [s for s in schemas if s in TENANT_EXTRA_SCHEMAS]

    main_tables = _list_main_tables(conn)
    drop_tables = [t for t in main_tables if t in TENANT_EXTRA_MAIN_TABLES]

    unknown_main = [t for t in main_tables if t not in CORE_MAIN_TABLES and t not in TENANT_EXTRA_MAIN_TABLES]
    if unknown_main:
        print(f"  [info] Tablas main no clasificadas (se conservan): {', '.join(unknown_main)}")

    return drop_schemas, drop_tables


def _apply_cleanup(
    conn: duckdb.DuckDBPyConnection,
    drop_schemas: list[str],
    drop_tables: list[str],
) -> None:
    for table in drop_tables:
        conn.execute(f'DROP TABLE IF EXISTS main."{table}"')
        print(f"  dropped table main.{table}")
    for schema in drop_schemas:
        conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        print(f"  dropped schema {schema}")


def _inspect_file(path: Path) -> None:
    print(f"\n=== {path} ===")
    conn = duckdb.connect(str(path), read_only=True)
    try:
        schemas = _list_schemas(conn)
        main_tables = _list_main_tables(conn)
        drop_schemas, drop_tables = _plan_cleanup(conn)
        print(f"  schemas: {schemas or '(none extra)'}")
        print(f"  main tables: {main_tables}")
        print(f"  would drop schemas: {drop_schemas or '(none)'}")
        print(f"  would drop main tables: {drop_tables or '(none)'}")
    finally:
        conn.close()


def _cleanup_file(path: Path, *, apply: bool) -> None:
    print(f"\n=== {path} ===")
    if not path.is_file():
        print("  [skip] archivo no encontrado")
        return
    conn = duckdb.connect(str(path), read_only=not apply)
    try:
        drop_schemas, drop_tables = _plan_cleanup(conn)
        if not drop_schemas and not drop_tables:
            print("  nothing to remove")
            return
        if not apply:
            print(f"  dry-run: schemas={drop_schemas}, tables={drop_tables}")
            return
        _apply_cleanup(conn, drop_schemas, drop_tables)
        print("  done")
    finally:
        conn.close()


def _iter_default_duckdb_files() -> list[Path]:
    root = _REPO_ROOT / "db" / "private"
    if not root.is_dir():
        return []
    return sorted(p for p in root.rglob("default.duckdb") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", default=[], help="Ruta a default.duckdb")
    parser.add_argument("--all-defaults", action="store_true", help="Todos los db/private/*/default.duckdb")
    parser.add_argument("--inspect", action="store_true", help="Solo listar (read-only)")
    parser.add_argument("--apply", action="store_true", help="Ejecutar DROP (requiere db-writer detenido o sin locks)")
    args = parser.parse_args()

    paths: list[Path] = [Path(p).expanduser() for p in args.path]
    if args.all_defaults:
        paths.extend(_iter_default_duckdb_files())
    if not paths:
        paths = [_REPO_ROOT / "db" / "private" / "1726618406" / "default.duckdb"]

    resolved = []
    for p in paths:
        rp = p if p.is_absolute() else (_REPO_ROOT / p).resolve()
        resolved.append(rp)

    if args.inspect or not args.apply:
        for rp in resolved:
            _inspect_file(rp)
        if not args.apply and not args.inspect:
            print("\nAñade --apply para ejecutar los DROP.")
        return 0

    for rp in resolved:
        _cleanup_file(rp, apply=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
