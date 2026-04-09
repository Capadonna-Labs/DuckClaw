#!/usr/bin/env python3
"""
Aplica DDL idempotente a todas las DuckDB bajo db/private/ y db/shared/, más rutas canónicas.

Ejecutar antes de PM2 (singleton writer + gateways en solo lectura).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

import duckdb

from duckclaw.forge.leila_schema import ensure_leila_mvp_schema
from duckclaw.gateway_db import ensure_usable_duckdb_file, get_gateway_db_path
from duckclaw.shared_db_grants import ensure_user_shared_db_access_table
from duckclaw.vaults import db_root, ensure_registry
from duckclaw.workers.loader import run_schema
from duckclaw.workers.manifest import load_manifest


def _resolve_extra_duckdb(raw: str, seen: set[Path], out: list[Path]) -> None:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (_REPO_ROOT / p).resolve()
    else:
        p = p.resolve()
    if p.suffix.lower() == ".duckdb" and p not in seen:
        seen.add(p)
        out.append(p)


def _iter_duckdb_targets(extra: list[str], *, only_extra: bool = False) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    if only_extra:
        for raw in extra:
            _resolve_extra_duckdb(raw, seen, out)
        return out
    root = db_root()
    for sub in ("private", "shared"):
        d = root / sub
        if d.is_dir():
            for p in d.rglob("*.duckdb"):
                r = p.resolve()
                if r not in seen:
                    seen.add(r)
                    out.append(p)
    for raw in extra:
        _resolve_extra_duckdb(raw, seen, out)
    gp = Path(get_gateway_db_path()).expanduser()
    if not gp.is_absolute():
        gp = (_REPO_ROOT / gp).resolve()
    else:
        gp = gp.resolve()
    if gp.suffix.lower() == ".duckdb" and gp.resolve() not in seen:
        seen.add(gp.resolve())
        out.append(gp)
    return out


class _ExecuteAdapter:
    __slots__ = ("_con",)

    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params=None) -> None:
        if params is not None:
            self._con.execute(sql, params)
        else:
            self._con.execute(sql)


def _ensure_war_room_schema_sql(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS war_room_core;")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS war_room_core.wr_members (
            tenant_id VARCHAR,
            user_id VARCHAR,
            username VARCHAR,
            clearance_level VARCHAR,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, user_id)
        );
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS war_room_core.wr_audit_log (
            event_id VARCHAR PRIMARY KEY,
            tenant_id VARCHAR,
            sender_id VARCHAR,
            target_agent VARCHAR,
            event_type VARCHAR,
            payload TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def _ensure_authorized_users(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS main.authorized_users (
            tenant_id VARCHAR,
            user_id VARCHAR,
            username VARCHAR,
            role VARCHAR DEFAULT 'user',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, user_id)
        );
        """
    )


def _ensure_fly_runtime_tables(con: duckdb.DuckDBPyConnection) -> None:
    """Tablas que on_the_fly_commands esperaba crear en runtime (ahora solo bootstrap + RO)."""
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_config (
            key VARCHAR PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS task_audit_log (
            task_id VARCHAR PRIMARY KEY,
            tenant_id VARCHAR NOT NULL,
            worker_id VARCHAR,
            query_prefix VARCHAR,
            status VARCHAR NOT NULL,
            duration_ms INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            plan_title VARCHAR
        );
        """
    )


def _collect_extensions(templates_root: Path) -> list[str]:
    names: set[str] = set()
    for manifest in templates_root.glob("*/manifest.yaml"):
        wid = manifest.parent.name
        try:
            spec = load_manifest(wid, templates_root)
        except Exception:
            continue
        for ext in getattr(spec, "duckdb_extensions", None) or []:
            e = str(ext).strip().lower()
            if e:
                names.add(e)
    return sorted(names)


def _install_extensions(con: duckdb.DuckDBPyConnection, extensions: list[str]) -> None:
    for ext in extensions:
        try:
            con.execute(f"INSTALL {ext};")
        except Exception:
            pass
        try:
            con.execute(f"LOAD {ext};")
        except Exception:
            pass


def bootstrap_file(path: Path, templates_root: Path, extensions: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_usable_duckdb_file(str(path))
    con = duckdb.connect(str(path), read_only=False)
    try:
        _install_extensions(con, extensions)
        _ensure_authorized_users(con)
        ensure_user_shared_db_access_table(_ExecuteAdapter(con))
        _ensure_war_room_schema_sql(con)
        _ensure_fly_runtime_tables(con)
        ensure_leila_mvp_schema(_ExecuteAdapter(con))
        for manifest in sorted(templates_root.glob("*/manifest.yaml")):
            wid = manifest.parent.name
            try:
                spec = load_manifest(wid, templates_root)
            except Exception:
                continue
            try:
                run_schema(_ExecuteAdapter(con), spec, seed_beliefs=False)
            except Exception as exc:
                print(f"  [warn] run_schema {wid}: {exc}", file=sys.stderr)
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap DuckDB schemas under db/")
    parser.add_argument(
        "extra_dbs",
        nargs="*",
        help="Rutas .duckdb adicionales (relativas al repo o absolutas)",
    )
    parser.add_argument(
        "--templates-root",
        type=Path,
        default=None,
        help="Raíz de forge/templates (por defecto packages/agents/.../templates)",
    )
    parser.add_argument(
        "--only-extra",
        action="store_true",
        help="Solo procesa rutas listadas en extra_dbs (no escanea db/private ni db/shared). Útil para un vault nuevo sin tocar BDs abiertas por el gateway.",
    )
    args = parser.parse_args()
    templates_root = args.templates_root
    if templates_root is None:
        templates_root = (
            _REPO_ROOT
            / "packages"
            / "agents"
            / "src"
            / "duckclaw"
            / "forge"
            / "templates"
        )
    if not templates_root.is_dir():
        print(f"No existe templates_root: {templates_root}", file=sys.stderr)
        return 1
    extensions = _collect_extensions(templates_root)
    print("ensure_registry (system.duckdb)...", flush=True)
    ensure_registry()
    if args.only_extra and not args.extra_dbs:
        print("Con --only-extra debes pasar al menos una ruta .duckdb.", file=sys.stderr)
        return 1
    targets = _iter_duckdb_targets(list(args.extra_dbs), only_extra=bool(args.only_extra))
    if not targets:
        print("No hay archivos .duckdb que procesar.", flush=True)
        return 0
    had_error = False
    for p in targets:
        print(f"Bootstrap: {p}", flush=True)
        try:
            bootstrap_file(p, templates_root, extensions)
        except Exception as exc:
            had_error = True
            print(f"  [error] {p}: {exc}", file=sys.stderr)
    if had_error:
        return 1
    print("OK.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
