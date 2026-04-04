"""
DuckDB para autorización en el API Gateway (Telegram Guard, war rooms, grants).

Si el grafo no puede abrir la misma DuckDB en modo exclusivo (otro proceso tiene el lock),
se usa una conexión de solo lectura a la misma ruta para que whitelist y miembros WR sigan funcionando.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pathlib import Path

from duckclaw.gateway_db import (
    GatewayDbEphemeralReadonly,
    get_gateway_db_path,
    get_war_room_acl_db_path,
)

_log = logging.getLogger("duckclaw.gateway.acl_db")


class ReadOnlyGatewayAclDb:
    """Subconjunto de la API DuckClaw: ``query`` con conexiones temporarias; ``execute`` sin efecto."""

    __slots__ = ("_path", "_read_only")

    _war_room_acl_readonly: bool = True

    def __init__(self, path: str) -> None:
        self._path = path
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

    def execute(self, _sql: str, _params: tuple | list | None = None) -> Any:
        return None


def get_gateway_acl_duckdb() -> tuple[Any, bool]:
    """Retorna ``(db, es_facade_readonly)``.

    ``graph_server.get_db()`` es siempre una facade RO efímera (sin handle persistente al .duckdb).
    """
    try:
        from duckclaw.graphs.graph_server import get_db

        db = get_db()
        if isinstance(db, (ReadOnlyGatewayAclDb, GatewayDbEphemeralReadonly)):
            return db, True
        try:
            db.execute("SELECT 1")
        except Exception as exc:
            _log.warning("get_db presente pero no usable; ACL en solo lectura: %s", exc)
            return ReadOnlyGatewayAclDb(get_gateway_db_path()), True
        return db, False
    except Exception as exc:
        _log.warning("get_db no disponible; ACL DuckDB solo lectura: %s", exc)
        return ReadOnlyGatewayAclDb(get_gateway_db_path()), True


def get_war_room_acl_duckdb() -> Any:
    """
    Conexión lógica para ``war_room_core`` (miembros / conteos).

    El gateway no mantiene un DuckClaw persistente al archivo; siempre lectura efímera sobre la ruta canónica.
    """
    wr_path = str(Path(get_war_room_acl_db_path()).expanduser().resolve())
    return ReadOnlyGatewayAclDb(wr_path)
