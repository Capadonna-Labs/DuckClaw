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
    "DUCKCLAW_QUANT_TRADER_DB_PATH",
    "DUCKCLAW_PQRSD_ASSISTANT_DB_PATH",
    "DUCKCLAW_AXIS_DB_PATH",
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




# Nombre canónico del archivo DuckDB del worker PQRSD-Assistant por usuario (bootstrap / plantillas).
PQRSD_ASSISTANT_VAULT_FILENAME = "pqrsd-assistantdb1.duckdb"


def default_pqrsd_assistant_vault_path(vault_user_id: str) -> str:
    """
    Ruta absoluta a ``db/private/<vault_user_id>/pqrsd-assistantdb1.duckdb``.

    Usada cuando ``DUCKCLAW_PQRSD_ASSISTANT_DB_PATH`` no está definido y el chat va al worker
    PQRSD-Assistant, para no heredar el vault dedicado del hub (p. ej. Finanz).
    """
    uid = (vault_user_id or "").strip() or "default"
    return resolve_env_duckdb_path(f"db/private/{uid}/{PQRSD_ASSISTANT_VAULT_FILENAME}")


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
    ``DUCKCLAW_SIATA_DB_PATH``, ``DUCKCLAW_QUANT_TRADER_DB_PATH``,
    ``DUCKCLAW_PQRSD_ASSISTANT_DB_PATH``, ``DUCKCLAW_AXIS_DB_PATH``, luego ``DUCKDB_PATH``; resuelta con
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


def iter_goals_ticker_duckdb_paths() -> list[str]:
    """
    Rutas ``.duckdb`` que escanea el ticker de ``/crons --delta`` (heartbeat / gateway embebido;
    claves internas ``goals_*`` en ``agent_config`` sin cambiar).

    Debe coincidir con ``services/heartbeat/main.py`` histórico: hub + ``db/private/*/*.duckdb``,
    o override ``DUCKCLAW_GOALS_TICKER_DB_PATH``. Centralizado para que ``/crons --delta off``
    limpie el schedule en **todos** los archivos donde pudo persistirse (multiplex Telegram).
    """
    raw = (os.getenv("DUCKCLAW_GOALS_TICKER_DB_PATH") or "").strip()
    if raw:
        return [resolve_env_duckdb_path(raw)]

    seen: set[str] = set()
    out: list[str] = []

    def _add(p: str) -> None:
        s = str(Path(p).expanduser().resolve())
        if s not in seen:
            seen.add(s)
            out.append(s)

    try:
        _add(get_gateway_db_path())
    except Exception:
        pass

    try:
        gw = Path(get_gateway_db_path()).expanduser().resolve()
        priv_root = gw.parent.parent
        if priv_root.is_dir() and priv_root.name == "private":
            for user_dir in sorted(priv_root.iterdir()):
                if not user_dir.is_dir():
                    continue
                for f in sorted(user_dir.glob("*.duckdb")):
                    _add(str(f))
    except Exception:
        pass

    return out


def iter_goals_delta_clear_duckdb_paths(*, primary_fly_db_path: str) -> list[str]:
    """
    Rutas a tocar al apagar ``/crons --delta`` desde la conexión ``fly_db`` actual.

    El ticker del heartbeat sigue usando ``iter_goals_ticker_duckdb_paths()`` (hub + todo
    ``db/private/*/*.duckdb``) para descubrir schedules. Limpiar el mismo conjunto desde el
    gateway abría decenas de archivos y competía por bloqueos con db-writer y otras sesiones.

    Aquí solo se devuelve: hub ``get_gateway_db_path()`` + ``*.duckdb`` del directorio
    ``.../private/<uid>/`` donde vive ``primary_fly_db_path`` (mismo criterio que
    ``parent.parent.name == "private"``). Si ``primary_fly_db_path`` no encaja en ese patrón,
    se añade al menos el archivo resuelto del primario además del hub.

    Override ``DUCKCLAW_GOALS_TICKER_DB_PATH``: un solo archivo, igual que el ticker.
    """
    raw = (os.getenv("DUCKCLAW_GOALS_TICKER_DB_PATH") or "").strip()
    if raw:
        return [resolve_env_duckdb_path(raw)]

    seen: set[str] = set()
    out: list[str] = []

    def _add(p: str) -> None:
        if not (p or "").strip():
            return
        try:
            s = str(Path(p).expanduser().resolve())
        except OSError:
            s = str(Path(p).expanduser())
        if s not in seen:
            seen.add(s)
            out.append(s)

    try:
        _add(get_gateway_db_path())
    except Exception:
        pass

    raw_primary = (primary_fly_db_path or "").strip()
    if not raw_primary:
        return out

    try:
        pp = Path(raw_primary).expanduser().resolve()
    except OSError:
        pp = Path(raw_primary).expanduser()

    if pp.suffix.lower() == ".duckdb" and pp.parent.is_dir():
        try:
            if pp.parent.parent.name == "private":
                for f in sorted(pp.parent.glob("*.duckdb")):
                    _add(str(f))
            else:
                _add(str(pp))
        except Exception:
            _add(str(pp))
    elif pp.is_file():
        _add(str(pp))

    return out
