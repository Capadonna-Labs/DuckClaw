"""
Ruta y acceso a la BD del API Gateway (microservicio services/api-gateway).

Usado por duckclaw.graphs.graph_server, forge, workers y scripts cuando necesitan
la misma DuckDB que usa el Gateway. Resuelve desde DUCKCLAW_DB_PATH o DUCKDB_PATH.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


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




def get_gateway_db_path() -> str:
    """
    Ruta del archivo DuckDB que usa el API Gateway (services/api-gateway).
    Resuelve DUCKCLAW_DB_PATH, luego DUCKDB_PATH; por defecto db/duckclaw.duckdb.
    No resuelve a ruta absoluta; el caller puede hacer Path(path).resolve() si necesita.
    """
    path = os.environ.get("DUCKCLAW_DB_PATH", "").strip()
    if path:
        return path
    return os.environ.get("DUCKDB_PATH", "db/duckclaw.duckdb").strip() or "db/duckclaw.duckdb"


def get_war_room_acl_db_path() -> str:
    """
    DuckDB donde vive ``war_room_core.wr_members`` para zero-trust en War Rooms.

    Si ``DUCKCLAW_WAR_ROOM_ACL_DB_PATH`` está definida (p. ej. finanzdb1 mientras el
    grafo del gateway usa jobhunterdb1), las comprobaciones WR leen esa ruta en solo
    lectura. Si no, coincide con ``get_gateway_db_path()``.
    """
    p = (os.environ.get("DUCKCLAW_WAR_ROOM_ACL_DB_PATH") or "").strip()
    if p:
        return p
    return get_gateway_db_path()


def get_gateway_db() -> Any:
    """
    Facade RO efímera a la misma ruta que el API Gateway (sin conexión persistente al archivo).

    Preferir pasar la conexión de la bóveda activa cuando el contexto sea multi-vault.
    """
    path = get_gateway_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return GatewayDbEphemeralReadonly(path)
