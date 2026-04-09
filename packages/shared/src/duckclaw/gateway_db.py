"""
Ruta y acceso a la BD del API Gateway (microservicio services/api-gateway).

Usado por duckclaw.graphs.graph_server, forge, workers y scripts cuando necesitan
la misma DuckDB que usa el Gateway. Resuelve desde ``DUCKCLAW_*_DB_PATH`` (multiplex)
y ``DUCKDB_PATH``; no usa ``DUCKCLAW_DB_PATH`` (eliminada).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

# Multiplex: solo rutas por worker (+ ACL WR opcional). Orden = prioridad del hub efectivo.
GATEWAY_DB_ENV_KEYS: tuple[str, ...] = (
    "DUCKCLAW_WAR_ROOM_ACL_DB_PATH",
    "DUCKCLAW_FINANZ_DB_PATH",
    "DUCKCLAW_JOB_HUNTER_DB_PATH",
    "DUCKCLAW_SIATA_DB_PATH",
    "DUCKDB_PATH",
)


class GatewayDbEphemeralReadonly:
    """
    Acceso RO al archivo del gateway sin mantener ``duckdb.connect`` abierto entre llamadas.
    Compatible con código que usa ``.query``, ``._path`` y ``._read_only`` (p. ej. append_task_audit → cola).
    """

    __slots__ = ("_path", "_read_only")

    def __init__(self, path: str) -> None:
        self._path = (path or "").strip() or get_gateway_db_path()
        self._read_only = True

    def query(self, sql: str, params: tuple | list | None = None) -> str:
        import duckdb

        con = duckdb.connect(self._path, read_only=True)
        try:
            if params is not None:
                result = con.execute(sql, params)
            else:
                result = con.execute(sql)
            rows = result.fetchall()
            names = [d[0] for d in result.description]
            out = [dict(zip(names, ("" if v is None else str(v) for v in row))) for row in rows]
            return json.dumps(out, ensure_ascii=False)
        finally:
            con.close()

    def execute(self, _sql: str, _params: Any = None) -> Any:
        return None




def ensure_usable_duckdb_file(path: str) -> None:
    """
    Garantiza que la ruta pueda abrirse con DuckDB.

    Un archivo ``*.duckdb`` de **0 bytes** (p. ej. creado con ``touch``) no es una base
    válida: DuckDB responde «not a valid DuckDB database file». En ese caso se elimina
    el placeholder para que ``duckclaw.DuckClaw`` o ``duckdb.connect`` creen una BD real
    al abrir en escritura.
    """
    p = (path or "").strip()
    if not p or p == ":memory:":
        return
    fp = Path(p).expanduser()
    try:
        fp = fp.resolve()
    except OSError:
        fp = Path(p).expanduser()
    try:
        fp.parent.mkdir(parents=True, exist_ok=True)
        if not fp.is_file():
            return
        if fp.stat().st_size == 0:
            fp.unlink()
    except OSError:
        return


def resolve_env_duckdb_path(raw: str) -> str:
    """
    Absolutiza una ruta de archivo DuckDB.

    Las rutas relativas (p. ej. ``DUCKCLAW_FINANZ_DB_PATH=db/private/.../x.duckdb``) se
    resuelven contra ``DUCKCLAW_REPO_ROOT``, no contra el cwd del proceso (PM2 puede
    arrancar fuera del repo y abrir otra copia del archivo).
    """
    p = Path((raw or "").strip()).expanduser()
    if not str(p):
        return ""
    if p.is_absolute():
        return str(p.resolve())
    rr = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    base = Path(rr).resolve() if rr else Path.cwd()
    return str((base / p).resolve())


def raw_gateway_db_path_from_environ() -> str:
    """Primera variable de entorno no vacía en ``GATEWAY_DB_ENV_KEYS``; fallback ``db/duckclaw.duckdb``."""
    for key in GATEWAY_DB_ENV_KEYS:
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    return "db/duckclaw.duckdb"


def raw_gateway_db_path_from_mapping(mapping: Mapping[str, Any]) -> str:
    """Igual que ``raw_gateway_db_path_from_environ`` pero leyendo un dict (p. ej. ``apps[].env`` del PM2 JSON)."""
    for key in GATEWAY_DB_ENV_KEYS:
        v = (str(mapping.get(key) or "")).strip()
        if v:
            return v
    return ""


def get_gateway_db_path() -> str:
    """
    Ruta absoluta del DuckDB del gateway (hub ACL / whitelist).

    Primera variable no vacía entre ``DUCKCLAW_WAR_ROOM_ACL_DB_PATH``,
    ``DUCKCLAW_FINANZ_DB_PATH``, ``DUCKCLAW_JOB_HUNTER_DB_PATH``,
    ``DUCKCLAW_SIATA_DB_PATH``, luego ``DUCKDB_PATH``; resuelta con
    ``resolve_env_duckdb_path``.
    """
    return resolve_env_duckdb_path(raw_gateway_db_path_from_environ())


def get_war_room_acl_db_path() -> str:
    """
    DuckDB donde vive ``war_room_core.wr_members`` para zero-trust en War Rooms.

    Si ``DUCKCLAW_WAR_ROOM_ACL_DB_PATH`` está definida (p. ej. finanzdb1 mientras el
    grafo del gateway usa jobhunterdb1), las comprobaciones WR leen esa ruta en solo
    lectura. Si no, coincide con ``get_gateway_db_path()``.
    """
    p = (os.environ.get("DUCKCLAW_WAR_ROOM_ACL_DB_PATH") or "").strip()
    if p:
        return resolve_env_duckdb_path(p)
    return get_gateway_db_path()


def get_gateway_db() -> Any:
    """
    Facade RO efímera a la misma ruta que el API Gateway (sin conexión persistente al archivo).

    Preferir pasar la conexión de la bóveda activa cuando el contexto sea multi-vault.
    """
    path = get_gateway_db_path()
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    return GatewayDbEphemeralReadonly(path)
