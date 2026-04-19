"""
Compatibilidad DuckDB: en el mismo proceso no se puede mezclar ``read_only=True`` y RW
sobre el mismo archivo (p. ej. worker LangGraph con vault RW + ``db/read`` en RO).

Ver comentario en ``on_the_fly_commands._team_whitelist_db`` y documentación DuckDB
sobre concurrencia en el mismo proceso.
"""

from __future__ import annotations

from typing import Any


def _is_ro_rw_configuration_conflict(exc: BaseException) -> bool:
    s = str(exc).lower()
    return "different configuration" in s and "same database" in s


def duckdb_connect_read_with_rw_fallback(db_path: str) -> Any:
    """``duckdb.connect`` para SELECT: intenta RO y cae a RW si ya hay conexión RW al archivo."""
    import duckdb

    try:
        return duckdb.connect(db_path, read_only=True)
    except Exception as exc:
        if _is_ro_rw_configuration_conflict(exc):
            return duckdb.connect(db_path, read_only=False)
        raise


def duckclaw_open_for_read_scan(db_path: str) -> Any:
    """``DuckClaw`` para lecturas puntuales (p. ej. goals ticker): RO primero, RW si hace falta."""
    from duckclaw import DuckClaw

    try:
        return DuckClaw(db_path, read_only=True)
    except Exception as exc:
        if _is_ro_rw_configuration_conflict(exc):
            return DuckClaw(db_path, read_only=False)
        raise
