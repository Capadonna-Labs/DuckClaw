#!/usr/bin/env python3
"""
Aplica DDL idempotente a todas las DuckDB bajo db/private/ y db/shared/, más rutas canónicas.

Ejecutar antes de PM2 (singleton writer + gateways en solo lectura).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv

    if os.environ.get("DUCKCLAW_DISABLE_DOTENV") != "1":
        load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass

import duckdb

from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.admin_console_users import ensure_admin_console_users_table, seed_admin_console_users_if_empty
from duckclaw.shared_db_grants import ensure_user_shared_db_access_table
from duckclaw.vaults import db_root, ensure_registry
from duckclaw.workers.loader import run_schema
from duckclaw.workers.manifest import load_manifest


def _bootstrap_path_skipped_default_scan(p: Path) -> bool:
    """Copias bajo dirs backup_* suelen ser snapshots rotos/incompatibles con el WAL."""
    return any(part.startswith("backup_") for part in p.parts)


def _resolve_extra_db(raw: str) -> Optional[Path]:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (_REPO_ROOT / p).resolve()
    else:
        p = p.resolve()
    if p.suffix.lower() != ".duckdb":
        return None
    return p


def _iter_duckdb_targets(extra: list[str], *, only_explicit: bool) -> list[Path]:
    """Si only_explicit=True, solo rutas pasadas como argumentos (sin rglob ni gateway implícito)."""
    seen: set[Path] = set()
    out: list[Path] = []
    if only_explicit:
        for raw in extra:
            rp = _resolve_extra_db(raw)
            if rp is None:
                print(f"  [skip] No es un .duckdb existente: {raw}", file=sys.stderr)
                continue
            if rp.resolve() not in seen:
                seen.add(rp.resolve())
                out.append(rp)
        return out

    root = db_root()
    for sub in ("private", "shared"):
        d = root / sub
        if d.is_dir():
            for p in d.rglob("*.duckdb"):
                if _bootstrap_path_skipped_default_scan(p):
                    continue
                r = p.resolve()
                if r not in seen:
                    seen.add(r)
                    out.append(p)
    for raw in extra:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = (_REPO_ROOT / p).resolve()
        else:
            p = p.resolve()
        if p.suffix.lower() == ".duckdb" and p.resolve() not in seen:
            seen.add(p.resolve())
            out.append(p)
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

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


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
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_usage_log (
            id VARCHAR PRIMARY KEY,
            tenant_id VARCHAR NOT NULL,
            session_id VARCHAR,
            worker_id VARCHAR,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd DOUBLE NOT NULL DEFAULT 0,
            model VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


def bootstrap_core_file(path: Path) -> None:
    """Perfil genérico Spawn: solo tablas núcleo (spec SPAWN_GENERIC_DEPLOY)."""
    from duckclaw.bootstrap_core import bootstrap_core_schema

    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path), read_only=False)
    try:
        try:
            con.execute("INSTALL json;")
            con.execute("LOAD json;")
        except Exception:
            pass
        adapter = _ExecuteAdapter(con)
        gp = Path(get_gateway_db_path()).expanduser()
        if not gp.is_absolute():
            gp = (_REPO_ROOT / gp).resolve()
        seed_admin = path.resolve() == gp.resolve()
        bootstrap_core_schema(adapter, seed_admin=seed_admin)
    finally:
        con.close()


def bootstrap_file(path: Path, templates_root: Path, extensions: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path), read_only=False)
    try:
        _install_extensions(con, extensions)
        _ensure_authorized_users(con)
        ensure_user_shared_db_access_table(_ExecuteAdapter(con))
        adapter = _ExecuteAdapter(con)
        ensure_admin_console_users_table(adapter)
        gp = Path(get_gateway_db_path()).expanduser()
        if not gp.is_absolute():
            gp = (_REPO_ROOT / gp).resolve()
        if path.resolve() == gp.resolve():
            seed_admin_console_users_if_empty(adapter)
        _ensure_fly_runtime_tables(con)
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
        "--only",
        action="store_true",
        help="Procesar únicamente los .duckdb listados como argumentos (sin escanear db/private|shared). Requiere al menos una ruta.",
    )
    parser.add_argument(
        "--core-only",
        action="store_true",
        help="Solo esquema núcleo (Spawn / perfil genérico). Sin dominios extra ni run_schema de templates.",
    )
    parser.add_argument(
        "--templates-root",
        type=Path,
        default=None,
        help="Raíz de forge/templates (por defecto packages/agents/.../templates)",
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
    if not args.core_only and not templates_root.is_dir():
        print(f"No existe templates_root: {templates_root}", file=sys.stderr)
        return 1
    extensions = _collect_extensions(templates_root) if templates_root.is_dir() else []
    print("ensure_registry (system.duckdb)...", flush=True)
    ensure_registry()
    if args.only and not args.extra_dbs:
        print("Uso: --only requiere al menos una ruta .duckdb.", file=sys.stderr)
        return 1
    only_explicit = bool(args.only) or bool(args.core_only)
    targets = _iter_duckdb_targets(list(args.extra_dbs), only_explicit=only_explicit)
    if args.core_only and not targets:
        default_db = os.environ.get("DUCKDB_PATH") or os.environ.get(
            "DUCKCLAW_DB_PATH", "db/private/default/duckclaw.duckdb"
        )
        rp = _resolve_extra_db(default_db)
        if rp is not None:
            targets = [rp]
    if not targets:
        print("No hay archivos .duckdb que procesar.", flush=True)
        return 0
    had_error = False
    for p in targets:
        print(f"Bootstrap{' (core-only)' if args.core_only else ''}: {p}", flush=True)
        try:
            if args.core_only:
                bootstrap_core_file(p)
            else:
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
