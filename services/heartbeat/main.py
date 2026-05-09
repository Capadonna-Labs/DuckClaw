from __future__ import annotations

"""
DuckClaw Heartbeat Daemon

Bucle asíncrono que evalúa homeostasis periódicamente y, cuando detecta anomalías,
inyecta un pensamiento interno ([SYSTEM_EVENT]) en el API Gateway.

Incluye un ticker de revisión /goals --delta (intervalo corto, independiente del
ciclo largo de homeostasis).
"""

import asyncio
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote

import httpx
import redis.asyncio as redis

from duckclaw import DuckClaw
from duckclaw.duckdb_read_compat import duckclaw_open_for_read_scan
from duckclaw.db_write_queue import enqueue_duckdb_write_sync
from duckclaw.forge.homeostasis import BeliefRegistry, HomeostasisManager
from duckclaw.gateway_db import get_gateway_db_path, iter_goals_ticker_duckdb_paths, resolve_env_duckdb_path
from duckclaw.graphs.on_the_fly_commands import (
    _GOALS_PROACTIVE_LAST_FIRE_KEY,
    _GOALS_PROACTIVE_TENANT_KEY,
    _GOALS_DELTA_META_KEY,
    build_goals_proactive_system_event_message,
    build_trading_tick_system_event_message,
    chat_id_from_goals_delta_config_key,
    get_chat_state,
    get_manager_goals,
)
from duckclaw.workers.factory import list_workers
from duckclaw.workers.manifest import load_manifest


logger = logging.getLogger("heartbeat")
logging.basicConfig(level=logging.INFO)


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
GATEWAY_URL = os.getenv(
    "GATEWAY_URL",
    "http://localhost:8000/api/v1/agent/chat",
)
HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "3600"))
GOALS_TICKER_POLL_SECONDS = int(os.getenv("GOALS_TICKER_POLL_SECONDS", "45"))
GITHUB_MCP_HEALTH_SECONDS = float(os.getenv("DUCKCLAW_GITHUB_MCP_HEALTH_SECONDS", "300"))
_GITHUB_PAT_401_AUDIT_COOLDOWN_KEY = "duckclaw:heartbeat:github_pat_401_audit_v1"
# POST a /api/v1/agent/chat para el tick de /goals: turnos Quant (varias tools + sandbox) suelen >120s
_GOALS_PROACTIVE_HTTP_TIMEOUT = float(os.environ.get("DUCKCLAW_GOALS_PROACTIVE_HTTP_TIMEOUT", "300"))
TAILSCALE_AUTH_KEY = os.getenv("DUCKCLAW_TAILSCALE_AUTH_KEY", "").strip()

# Una advertencia corta por ruta cuando el .duckdb no abre (p. ej. WAL inconsistente); evita spam cada poll.
_GOALS_WAL_WARNED_PATHS: set[str] = set()


def _short_duckdb_exception_message(exc: BaseException) -> str:
    """Una línea útil; DuckDB adjunta párrafos de ayuda y stack al mensaje."""
    s = str(exc)
    for sep in (
        "Stack Trace:",
        "This error signals an assertion failure",
        "For more information, see",
    ):
        if sep in s:
            s = s.split(sep, 1)[0].strip()
    s = " ".join(s.split())
    if len(s) > 320:
        s = s[:317] + "..."
    return s


def _goals_proactive_db_wal_or_corruption(exc: BaseException) -> bool:
    """WAL dañado o estado interno DuckDB al abrir (no es 'tabla ausente' ni lock)."""
    m = str(exc).lower()
    if "failure while replaying" in m:
        return True
    if "replaying wal" in m:
        return True
    if "wal file" in m and "internal" in m:
        return True
    if "getdefaultdatabase" in m and "no default database" in m:
        return True
    return False


def _agent_config_chat_key(chat_id: Any, suffix: str) -> str:
    try:
        cid = int(str(chat_id).strip())
        return f"chat_{cid}_{suffix}"
    except (TypeError, ValueError):
        return f"chat_{str(chat_id)[:64]}_{suffix}"


async def _enqueue_chat_state_write(
    *,
    db_path: str,
    chat_id: Any,
    tenant_id: str,
    key: str,
    value: str,
) -> None:
    query = (
        "INSERT INTO agent_config (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"
    )
    ck = _agent_config_chat_key(chat_id, key)
    await asyncio.to_thread(
        enqueue_duckdb_write_sync,
        db_path=db_path,
        query=query,
        params=[ck, str(value)[:16384]],
        user_id=str(chat_id),
        tenant_id=str(tenant_id or "default"),
    )


def _goals_ticker_scan_db_paths() -> List[str]:
    """Delega en ``iter_goals_ticker_duckdb_paths`` (paquete shared) para una sola fuente de verdad."""
    return iter_goals_ticker_duckdb_paths()


def _goals_proactive_db_open_error_is_expected(exc: BaseException) -> bool:
    """Evita WARNING ruidoso al escanear todo *.duckdb (legacy, sin esquema, o bloqueado)."""
    msg = str(exc).lower()
    if "agent_config" in msg and ("does not exist" in msg or "catalog error" in msg):
        return True
    if "could not set lock" in msg or "conflicting lock" in msg:
        return True
    return False


def _resolve_trading_session_vault_path(session_uid: str, candidate_paths: List[str]) -> str | None:
    """
    Encuentra el .duckdb donde vive quant_core.trading_sessions (ACTIVE) para este session_uid.
    El ticker goals puede leer agent_config en finanzdb pero la sesión vive en quant_traderdb1.duckdb;
    el POST al gateway debe usar esa bóveda o evaluate_cfd_state y OHLCV ven vacíos.
    """
    uid = (session_uid or "").strip()
    for p in candidate_paths:
        try:
            with DuckClaw(p, read_only=True) as dbr:
                raw = dbr.query(
                    "SELECT session_uid, status FROM quant_core.trading_sessions WHERE id = 'active' LIMIT 1"
                )
                rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except Exception:
            continue
        if not rows or not isinstance(rows[0], dict):
            continue
        row = rows[0]
        if str(row.get("status") or "").strip().upper() != "ACTIVE":
            continue
        row_uid = str(row.get("session_uid") or "").strip()
        if uid and row_uid and uid != row_uid:
            continue
        return str(Path(p).expanduser().resolve())
    return None


def _resolve_quant_trader_vault_path(candidate_paths: List[str]) -> str | None:
    """
    Misma bóveda que el webhook multiplex Quant-Trader (quant_traderdb1.duckdb).
    Sin esto, el POST interno cae en dedicated gateway (p. ej. finanzdb) y quant_core.* queda vacío.
    """
    raw = (os.getenv("DUCKCLAW_QUANT_TRADER_DB_PATH") or "").strip()
    if raw:
        try:
            return str(Path(resolve_env_duckdb_path(raw)).expanduser().resolve())
        except Exception:
            pass
    for p in candidate_paths:
        if "quant_trader" in Path(p).name.lower():
            try:
                return str(Path(p).expanduser().resolve())
            except Exception:
                continue
    return None


def _agent_chat_url_for_worker(gateway_url: str, worker_id: str) -> str:
    base = gateway_url.rstrip("/").rsplit("/", 1)[0]
    return f"{base}/{quote(worker_id, safe='')}/chat?deliver_outbound=1"


async def check_cooldown(r: redis.Redis, tenant_id: str, alert_type: str) -> bool:
    """Verifica si ya enviamos esta alerta recientemente (Anti-Spam)."""
    key = f"cooldown:{tenant_id}:{alert_type}"
    if await r.exists(key):
        return False
    # Bloquear futuras alertas de este tipo por 24 horas (86400 segundos)
    await r.setex(key, 86400, "locked")
    return True


async def _evaluate_homeostasis() -> List[Dict[str, Any]]:
    """
    Recorre workers con homeostasis_config y evalúa sus beliefs.

    Devuelve una lista de dicts con:
    - tenant_id: normalmente el schema/worker_id (ej. finance_worker/finanz)
    - belief_key
    - observed_value (target como proxy cuando no hay observación externa)
    - admin_chat_id: chat al que notificar (por ahora, configurado vía env)
    """
    db_path = get_gateway_db_path()
    db = DuckClaw(db_path)

    anomalies: List[Dict[str, Any]] = []

    # ADMIN_CHAT_ID global por ahora; a futuro podría venir de una tabla de configuración por tenant.
    default_admin_chat_id = os.getenv("DUCKCLAW_ADMIN_CHAT_ID", "").strip()

    for wid in list_workers():
        try:
            spec = load_manifest(wid)
            config = getattr(spec, "homeostasis_config", None) or {}
            registry = BeliefRegistry.from_config(config)
            if not registry.beliefs:
                continue
            schema = spec.schema_name
            manager = HomeostasisManager(db=db, schema=schema, registry=registry)

            # Por simplicidad inicial, usamos target como observed_value para forzar evaluación.
            for belief in registry.beliefs:
                observed_value = belief.target
                plan = manager.check(
                    belief.key,
                    observed_value,
                    auto_update=True,
                    invoke_restoration=False,
                )
                if plan.get("action") == "restore":
                    anomalies.append(
                        {
                            "tenant_id": schema,
                            "belief_key": plan.get("belief_key", belief.key),
                            "observed_value": plan.get("observed", observed_value),
                            "admin_chat_id": default_admin_chat_id,
                        }
                    )
        except Exception as e:  # noqa: BLE001
            logger.exception("Error evaluando homeostasis para worker %s: %s", wid, e)

    return anomalies


async def _run_goals_proactive_tick() -> None:
    """Escanea agent_config y dispara SYSTEM_EVENT de revisión /goals cuando toca."""
    now = time.time()
    scan_paths = _goals_ticker_scan_db_paths()
    headers: Dict[str, str] = {}
    if TAILSCALE_AUTH_KEY:
        headers["X-Tailscale-Auth-Key"] = TAILSCALE_AUTH_KEY

    for db_path in scan_paths:
        await _run_goals_proactive_tick_one_db(
            db_path,
            now=now,
            headers=headers,
            scan_paths_n=len(scan_paths),
            all_scan_paths=scan_paths,
        )


async def _run_goals_proactive_tick_one_db(
    db_path: str,
    *,
    now: float,
    headers: Dict[str, str],
    scan_paths_n: int,
    all_scan_paths: List[str],
) -> None:
    try:
        with duckclaw_open_for_read_scan(db_path) as db_ro:
            raw = db_ro.query(
                "SELECT key, value FROM agent_config WHERE key LIKE 'chat_%_goals_delta_seconds'"
            )
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception as exc:  # noqa: BLE001
        path_key = str(Path(db_path).expanduser().resolve())
        if _goals_proactive_db_open_error_is_expected(exc):
            logger.debug(
                "goals_proactive: omitiendo lectura agent_config (%s): %s",
                db_path,
                exc,
            )
        elif _goals_proactive_db_wal_or_corruption(exc):
            if path_key not in _GOALS_WAL_WARNED_PATHS:
                _GOALS_WAL_WARNED_PATHS.add(path_key)
                logger.warning(
                    "goals_proactive: bóveda ilegible (WAL/corrupción); se omite goals ticker para %s. "
                    "Detener servicios que usen el archivo, respaldar .duckdb y .wal, reparar o regenerar (p. ej. bootstrap). %s",
                    db_path,
                    _short_duckdb_exception_message(exc),
                )
            else:
                logger.debug(
                    "goals_proactive: omitiendo %s (DuckDB no disponible)",
                    db_path,
                )
        else:
            logger.warning("goals_proactive: no se pudo leer agent_config (%s): %s", db_path, exc)
        return

    if not rows:
        return

    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "")
        chat_id = chat_id_from_goals_delta_config_key(key)
        if not chat_id:
            continue
        try:
            delta_s = int(str(row.get("value") or "0").strip() or "0")
        except ValueError:
            continue
        if delta_s <= 0:
            continue

        with duckclaw_open_for_read_scan(db_path) as db:
            goals = get_manager_goals(db, chat_id)
            meta_raw_pre = (get_chat_state(db, chat_id, _GOALS_DELTA_META_KEY) or "").strip()
            meta_pre: Dict[str, Any] = {}
            if meta_raw_pre:
                try:
                    _mp = json.loads(meta_raw_pre)
                    if isinstance(_mp, dict):
                        meta_pre = _mp
                except Exception:
                    meta_pre = {}
            tenant_id = (get_chat_state(db, chat_id, _GOALS_PROACTIVE_TENANT_KEY) or "").strip()
            worker_id = (get_chat_state(db, chat_id, "worker_id") or "").strip()
            if (not worker_id or worker_id.lower() == "manager") and tenant_id.lower() == "cuantitativo":
                worker_id = "Quant-Trader"
            _wid_pre = (worker_id or "").strip()
            _is_qt = _wid_pre == "Quant-Trader" or _wid_pre.lower() in ("quant-trader", "quant_trader")
            _ts_trigger = str(meta_pre.get("trigger") or "").strip().lower() == "trading_session"
            allow_empty_goals = bool(not goals and _ts_trigger and _is_qt)
            if not goals and not allow_empty_goals:
                logger.info(
                    "goals_proactive: chat=%s sin goals; limpiando delta",
                    chat_id,
                )
                try:
                    for _k, _v in (
                        ("goals_delta_seconds", "0"),
                        ("goals_proactive_last_fire", ""),
                        ("goals_proactive_anchor", ""),
                        ("goals_proactive_tenant_id", ""),
                        ("goals_delta_anchor", ""),
                        ("goals_delta_meta", ""),
                    ):
                        await _enqueue_chat_state_write(
                            db_path=db_path,
                            chat_id=chat_id,
                            tenant_id="default",
                            key=_k,
                            value=_v,
                        )
                except Exception as _exc:
                    logger.warning(
                        "goals_proactive: error al limpiar delta chat=%s: %s",
                        chat_id,
                        _exc,
                    )
                continue

            if not worker_id or worker_id.lower() == "manager":
                logger.debug(
                    "goals_proactive: omitiendo chat=%s (worker_id=%r tenant_id=%r)",
                    chat_id,
                    worker_id,
                    tenant_id,
                )
                continue

            if not tenant_id:
                logger.warning(
                    "goals_proactive: chat=%s sin goals_proactive_tenant_id; "
                    "repite /goals --delta tras actualizar",
                    chat_id,
                )
                continue

            last_raw = (get_chat_state(db, chat_id, _GOALS_PROACTIVE_LAST_FIRE_KEY) or "").strip()
            try:
                last_fire = float(last_raw) if last_raw else 0.0
            except ValueError:
                last_fire = 0.0
            if last_fire > 0 and (now - last_fire) < float(delta_s):
                continue
            meta_raw = (get_chat_state(db, chat_id, _GOALS_DELTA_META_KEY) or "").strip()
            meta: Dict[str, Any] = {}
            if meta_raw:
                try:
                    maybe_meta = json.loads(meta_raw)
                    if isinstance(maybe_meta, dict):
                        meta = maybe_meta
                except Exception:
                    meta = {}
            if str(meta.get("trigger") or "").strip().lower() == "trading_session":
                session_uid = str(meta.get("session_uid") or "").strip()
                tickers: list[str] = []
                mode = "paper"
                signal_threshold = "GAS"
                objective = "maximize_pnl"
                if session_uid:
                    try:
                        sess_db_path = (
                            _resolve_trading_session_vault_path(session_uid, all_scan_paths) or db_path
                        )
                        _db_same = str(Path(sess_db_path).resolve()) == str(
                            Path(getattr(db, "_path", "") or db_path).resolve()
                        )
                        if _db_same:
                            raw_sess = db.query(
                                "SELECT mode, tickers, session_goal, session_uid, status "
                                "FROM quant_core.trading_sessions WHERE id = 'active' LIMIT 1"
                            )
                        else:
                            with DuckClaw(sess_db_path, read_only=True) as sess_conn:
                                raw_sess = sess_conn.query(
                                    "SELECT mode, tickers, session_goal, session_uid, status "
                                    "FROM quant_core.trading_sessions WHERE id = 'active' LIMIT 1"
                                )
                        sess_rows = json.loads(raw_sess) if isinstance(raw_sess, str) else (raw_sess or [])
                        if sess_rows and isinstance(sess_rows[0], dict):
                            sess_row = sess_rows[0]
                            if str(sess_row.get("status") or "").strip().upper() != "ACTIVE":
                                message = "[SYSTEM_EVENT: No hay sesión activa. Tick cancelado.]"
                            else:
                                mode = str(sess_row.get("mode") or "paper").strip().lower() or "paper"
                                tickers_csv = str(sess_row.get("tickers") or "").strip()
                                if tickers_csv:
                                    tickers = [x.strip().upper() for x in tickers_csv.split(",") if x.strip()]
                                goal_raw = sess_row.get("session_goal")
                                try:
                                    gobj = (
                                        goal_raw
                                        if isinstance(goal_raw, dict)
                                        else json.loads(str(goal_raw or "{}"))
                                    )
                                except Exception:
                                    gobj = {}
                                if isinstance(gobj, dict):
                                    signal_threshold = str(gobj.get("signal_threshold") or "GAS").strip().upper() or "GAS"
                                    objective = str(gobj.get("objective") or "maximize_pnl").strip().lower() or "maximize_pnl"
                                session_uid = str(sess_row.get("session_uid") or session_uid).strip()
                                message = build_trading_tick_system_event_message(
                                    session_uid=session_uid,
                                    tickers=tickers,
                                    mode=mode,
                                    signal_threshold=signal_threshold,
                                    objective=objective,
                                )
                        else:
                            message = "[SYSTEM_EVENT: No hay sesión activa. Tick cancelado.]"
                    except Exception:
                        message = "[SYSTEM_EVENT: No se pudo resolver la sesión activa. Tick cancelado.]"
                else:
                    message = "[SYSTEM_EVENT: No hay session_uid en goals_delta_meta. Tick cancelado.]"
            else:
                trading_obj: str | None = None
                if _is_qt:
                    _qpath = _resolve_quant_trader_vault_path(all_scan_paths)
                    if _qpath:
                        try:
                            with DuckClaw(_qpath, read_only=True) as _qdb:
                                raw_sg = _qdb.query(
                                    "SELECT session_goal FROM quant_core.trading_sessions "
                                    "WHERE id = 'active' LIMIT 1"
                                )
                            srows = (
                                json.loads(raw_sg) if isinstance(raw_sg, str) else (raw_sg or [])
                            )
                            if srows and isinstance(srows[0], dict):
                                sgr = srows[0].get("session_goal")
                                if isinstance(sgr, str):
                                    sgr = json.loads(sgr)
                                if isinstance(sgr, dict):
                                    o = str(sgr.get("objective") or "").strip().lower()
                                    if o in (
                                        "maximize_pnl",
                                        "rebalance_hrp",
                                        "overnight_gap_squeeze",
                                    ):
                                        trading_obj = o
                        except Exception:
                            trading_obj = None
                message = build_goals_proactive_system_event_message(
                    goals, trading_session_objective=trading_obj
                )

        _wid = (worker_id or "").strip()
        vault_for_gateway = str(Path(db_path).expanduser().resolve())
        _qt_vault: str | None = None
        if _wid == "Quant-Trader" or _wid.lower() in ("quant-trader", "quant_trader"):
            _qt_vault = _resolve_quant_trader_vault_path(all_scan_paths)
            if _qt_vault:
                vault_for_gateway = _qt_vault
        payload = {
            "message": message,
            "chat_id": str(chat_id),
            "user_id": str(chat_id),
            "username": "Usuario",
            "chat_type": "private",
            "tenant_id": tenant_id,
            "is_system_prompt": True,
            "skip_session_lock": True,
        }
        if _qt_vault:
            payload["vault_db_path"] = _qt_vault
        url = _agent_chat_url_for_worker(GATEWAY_URL, worker_id)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    params={"tenant_id": tenant_id, "deliver_outbound": "1"},
                    json=payload,
                    headers=headers,
                    timeout=_GOALS_PROACTIVE_HTTP_TIMEOUT,
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "goals_proactive: error HTTP chat=%s worker=%s: %s",
                chat_id,
                worker_id,
                exc,
            )
            continue

        if 200 <= resp.status_code < 300:
            _resp_text = ""
            try:
                _payload = resp.json() if (resp.text or "").strip().startswith("{") else {}
                if isinstance(_payload, dict):
                    _resp_text = str(_payload.get("response") or "").strip()
            except Exception:
                _resp_text = ""
            await _enqueue_chat_state_write(
                db_path=db_path,
                chat_id=chat_id,
                tenant_id=tenant_id or "default",
                key=_GOALS_PROACTIVE_LAST_FIRE_KEY,
                value=str(now),
            )
            try:
                if _resp_text:
                    _m_curr = re.search(
                        r"(?:PnL no realizado=\$|PnL no realizado total \(snapshot\):\s*\$)"
                        r"([\-0-9,]+(?:\.[0-9]+)?)",
                        _resp_text,
                    )
                    _m_prev = re.search(r"PnL anterior=\$([\-0-9,]+(?:\.[0-9]+)?)", _resp_text)
                    _m_pct = re.search(r"Cambio vs anterior=([+\-]?[0-9]+(?:\.[0-9]+)?)%", _resp_text)
                    _curr_txt = _m_curr.group(1).replace(",", "") if _m_curr else ""
                    _prev_txt = _m_prev.group(1).replace(",", "") if _m_prev else ""
                    _pct_txt = _m_pct.group(1) if _m_pct else ""
                    if _curr_txt:
                        await _enqueue_chat_state_write(
                            db_path=db_path,
                            chat_id=chat_id,
                            tenant_id=tenant_id or "default",
                            key="trading_session_last_pnl",
                            value=_curr_txt,
                        )
                    await _enqueue_chat_state_write(
                        db_path=db_path,
                        chat_id=chat_id,
                        tenant_id=tenant_id or "default",
                        key="trading_session_prev_pnl",
                        value=_prev_txt,
                    )
                    await _enqueue_chat_state_write(
                        db_path=db_path,
                        chat_id=chat_id,
                        tenant_id=tenant_id or "default",
                        key="trading_session_pct_change",
                        value=_pct_txt,
                    )
            except Exception as _exc:
                logger.debug(
                    "goals_proactive: persist PnL chat_state chat=%s: %s",
                    chat_id,
                    _exc,
                )
            try:
                if '"type":"TRADING_TICK"' in message or '"type": "TRADING_TICK"' in message:
                    start = message.find("{")
                    end = message.rfind("}")
                    payload_ev = json.loads(message[start : end + 1]) if start >= 0 and end > start else {}
                    if isinstance(payload_ev, dict):
                        uid = str(payload_ev.get("session_uid") or "").strip()
                        tickers = payload_ev.get("tickers") if isinstance(payload_ev.get("tickers"), list) else []
                        await asyncio.to_thread(
                            enqueue_duckdb_write_sync,
                            db_path=db_path,
                            query=(
                                "INSERT INTO quant_core.session_ticks "
                                "(id, session_uid, tick_number, tickers_processed, signals_proposed, cfd_summary, outcome) "
                                "VALUES (gen_random_uuid(), ?, COALESCE((SELECT MAX(tick_number)+1 FROM quant_core.session_ticks WHERE session_uid=?), 1), ?, 0, ?, ?)"
                            ),
                            params=[
                                uid,
                                uid,
                                [str(t).strip().upper() for t in tickers if str(t).strip()],
                                json.dumps({"source": "heartbeat"}, ensure_ascii=False),
                                "ALIGNED",
                            ],
                            user_id=str(chat_id),
                            tenant_id=str(tenant_id or "default"),
                        )
            except Exception:
                pass
            logger.info(
                "goals_proactive: tick OK chat=%s worker=%s",
                chat_id,
                worker_id,
            )
        else:
            logger.warning(
                "goals_proactive: HTTP %s chat=%s body=%s",
                resp.status_code,
                chat_id,
                (resp.text or "")[:200],
            )


async def _docker_daemon_reachable() -> bool:
    """Comprueba si el CLI ``docker`` puede hablar con el daemon (OrbStack / Docker Desktop)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            "info",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return False
    try:
        rc = await asyncio.wait_for(proc.wait(), timeout=18.0)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return False
    return rc == 0


async def _github_pat_api_user_status(token: str) -> int | None:
    """GET /user; retorna status HTTP o None si error de red/timeouts. No loguear el token."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=15.0,
            )
            return int(resp.status_code)
    except Exception:
        return None


def _enqueue_github_pat_invalid_task_audit() -> None:
    """Mejor esfuerzo: registrar en task_audit_log vía singleton writer (401 PAT)."""
    from duckclaw.db_write_queue import enqueue_duckdb_write_sync, poll_task_status_sync

    dp = ""
    try:
        dp = str(get_gateway_db_path() or "").strip()
    except Exception:
        return
    if not dp:
        return
    db_path = str(Path(dp).expanduser().resolve())
    task_id = f"TASK-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    qp = "GitHub PAT inválido o expirado (401) — revisa GITHUB_TOKEN en .env"
    plan = "github_pat_invalid"
    tenant = (os.environ.get("DUCKCLAW_GITHUB_MCP_HEALTH_AUDIT_TENANT") or "system").strip() or "system"
    sql = (
        "INSERT INTO task_audit_log (task_id, tenant_id, worker_id, query_prefix, status, duration_ms, plan_title) "
        "VALUES (?, ?, ?, ?, 'FAILED', 0, ?)"
    )
    tid = enqueue_duckdb_write_sync(
        db_path=db_path,
        query=sql,
        params=[task_id, tenant, "heartbeat", qp, plan],
        user_id="default",
        tenant_id=tenant,
    )
    poll_task_status_sync(tid, timeout_sec=12.0)


async def _github_mcp_health_tick(r: redis.Redis) -> None:
    docker_ok = await _docker_daemon_reachable()
    if not docker_ok:
        logger.warning(
            "GitHub MCP health: docker no responde (`docker info`). GitHub MCP desde gateway requerirá Docker."
        )

    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return

    status = await _github_pat_api_user_status(token)
    if status is None:
        logger.warning("GitHub MCP health: error de red o timeout al llamar api.github.com/user")
        return
    if status == 200:
        logger.debug("GitHub MCP health: PAT OK (api.github.com/user 200)")
        return
    if status == 401:
        logger.error("GitHub MCP health: GITHUB_TOKEN inválido o expirado (401)")
        try:
            set_ok = await r.set(_GITHUB_PAT_401_AUDIT_COOLDOWN_KEY, "1", ex=3600, nx=True)
        except Exception:
            set_ok = None
        if set_ok:
            await asyncio.to_thread(_enqueue_github_pat_invalid_task_audit)
        return

    logger.warning("GitHub MCP health: api.github.com/user → HTTP %s", status)


async def run_heartbeat() -> None:
    r = redis.from_url(REDIS_URL)
    interval = float(HEARTBEAT_INTERVAL_SECONDS)
    poll = max(5, GOALS_TICKER_POLL_SECONDS)
    # Primer ciclo debe poder evaluar homeostasis de inmediato (antes: evaluar y luego sleep).
    last_homeo = time.time() - interval
    last_github_health = 0.0

    while True:
        try:
            await _run_goals_proactive_tick()
        except Exception as exc:  # noqa: BLE001
            logger.exception("goals_proactive: ciclo: %s", exc)

        now_mono = time.monotonic()
        if now_mono - last_github_health >= GITHUB_MCP_HEALTH_SECONDS:
            try:
                await _github_mcp_health_tick(r)
            except Exception as exc:  # noqa: BLE001
                logger.exception("GitHub MCP health: tick falló: %s", exc)
            last_github_health = now_mono

        now = time.time()
        if now - last_homeo >= interval:
            logger.info("Iniciando ciclo de evaluación de Homeostasis...")
            try:
                anomalies = await _evaluate_homeostasis()
                logger.info("Anomalías encontradas: %s", len(anomalies))

                for anomaly in anomalies:
                    tenant_id = str(anomaly.get("tenant_id", "")).strip() or "default"
                    alert_type = str(anomaly.get("belief_key", "")).strip() or "unknown"
                    admin_chat_id = str(anomaly.get("admin_chat_id", "")).strip()
                    observed_value = anomaly.get("observed_value")

                    if not admin_chat_id:
                        logger.warning(
                            "Anomalía sin admin_chat_id (tenant_id=%s, alert_type=%s)",
                            tenant_id,
                            alert_type,
                        )
                        continue

                    if not await check_cooldown(r, tenant_id, alert_type):
                        logger.info(
                            "Cooldown activo para tenant=%s alert_type=%s; no se envía.",
                            tenant_id,
                            alert_type,
                        )
                        continue

                    logger.info(
                        "Anomalía detectada en tenant=%s, belief=%s. Inyectando pensamiento...",
                        tenant_id,
                        alert_type,
                    )

                    message = (
                        "[SYSTEM_EVENT: Anomalía detectada en "
                        f"{alert_type}. Valor actual: {observed_value}. "
                        "Evalúa la situación y notifica al usuario si es crítico.]"
                    )
                    payload = {
                        "message": message,
                        "chat_id": admin_chat_id,
                        "is_system_prompt": True,
                    }

                    headers: Dict[str, str] = {}
                    if TAILSCALE_AUTH_KEY:
                        headers["X-Tailscale-Auth-Key"] = TAILSCALE_AUTH_KEY

                    try:
                        async with httpx.AsyncClient() as client:
                            await client.post(
                                GATEWAY_URL,
                                params={"tenant_id": tenant_id, "worker_id": "finanz"},
                                json=payload,
                                headers=headers,
                                timeout=30,
                            )
                    except Exception as e:  # noqa: BLE001
                        logger.exception("Error enviando evento al Gateway: %s", e)

            except Exception as e:  # noqa: BLE001
                logger.exception("Error en ciclo de heartbeat: %s", e)

            last_homeo = time.time()

        await asyncio.sleep(poll)


if __name__ == "__main__":
    asyncio.run(run_heartbeat())
