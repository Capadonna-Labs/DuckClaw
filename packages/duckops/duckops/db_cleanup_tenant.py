#!/usr/bin/env python3
"""
Elimina esquemas/tablas indicados explícitamente de archivos default.duckdb.

Conserva tablas core en ``main``: agent_config, authorized_users, task_audit_log,
user_shared_db_access.

Uso:
  uv run duckops db cleanup-default-tenant-schemas --inspect
  uv run duckops db cleanup-default-tenant-schemas --path db/private/1726618406/default.duckdb --apply
  uv run duckops db cleanup-default-tenant-schemas --all-defaults --apply
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Collection
from pathlib import Path

from duckops.paths import repo_root

_REPO_ROOT = repo_root()
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import duckdb

# Defaults no destructivos: cualquier cleanup de dominio debe pedirse por CLI.
DEFAULT_DROP_MAIN_TABLES: tuple[str, ...] = ()

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


def _normalise_names(names: Collection[str]) -> set[str]:
    return {str(name).strip() for name in names if str(name).strip()}


def _plan_cleanup(
    conn: duckdb.DuckDBPyConnection,
    *,
    drop_schema_names: Collection[str] = (),
    drop_main_table_names: Collection[str] = DEFAULT_DROP_MAIN_TABLES,
) -> tuple[list[str], list[str]]:
    schemas = _list_schemas(conn)
    configured_schemas = _normalise_names(drop_schema_names)
    drop_schemas = [s for s in schemas if s in configured_schemas]

    main_tables = _list_main_tables(conn)
    configured_main_tables = _normalise_names(drop_main_table_names)
    drop_tables = [t for t in main_tables if t in configured_main_tables]

    unknown_main = [t for t in main_tables if t not in CORE_MAIN_TABLES and t not in configured_main_tables]
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


def _inspect_file(
    path: Path,
    *,
    drop_schema_names: Collection[str],
    drop_main_table_names: Collection[str],
) -> None:
    print(f"\n=== {path} ===")
    conn = duckdb.connect(str(path), read_only=True)
    try:
        schemas = _list_schemas(conn)
        main_tables = _list_main_tables(conn)
        drop_schemas, drop_tables = _plan_cleanup(
            conn,
            drop_schema_names=drop_schema_names,
            drop_main_table_names=drop_main_table_names,
        )
        print(f"  schemas: {schemas or '(none extra)'}")
        print(f"  main tables: {main_tables}")
        print(f"  would drop schemas: {drop_schemas or '(none)'}")
        print(f"  would drop main tables: {drop_tables or '(none)'}")
    finally:
        conn.close()


def _cleanup_file(
    path: Path,
    *,
    apply: bool,
    drop_schema_names: Collection[str],
    drop_main_table_names: Collection[str],
) -> None:
    print(f"\n=== {path} ===")
    if not path.is_file():
        print("  [skip] archivo no encontrado")
        return
    conn = duckdb.connect(str(path), read_only=not apply)
    try:
        drop_schemas, drop_tables = _plan_cleanup(
            conn,
            drop_schema_names=drop_schema_names,
            drop_main_table_names=drop_main_table_names,
        )
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
    parser.add_argument("--drop-schema", action="append", default=[], help="Schema a borrar explícitamente")
    parser.add_argument("--drop-main-table", action="append", default=[], help="Tabla main a borrar explícitamente")
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
            _inspect_file(
                rp,
                drop_schema_names=args.drop_schema,
                drop_main_table_names=args.drop_main_table,
            )
        if not args.apply and not args.inspect:
            print("\nAñade --apply para ejecutar los DROP.")
        return 0

    for rp in resolved:
        _cleanup_file(
            rp,
            apply=True,
            drop_schema_names=args.drop_schema,
            drop_main_table_names=args.drop_main_table,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
