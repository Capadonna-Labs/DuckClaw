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
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote

import httpx
import redis.asyncio as redis

from duckclaw import DuckClaw
from duckclaw.db_write_queue import enqueue_duckdb_write_sync
from duckclaw.forge.homeostasis import BeliefRegistry, HomeostasisManager
from duckclaw.gateway_db import get_gateway_db_path
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
TAILSCALE_AUTH_KEY = os.getenv("DUCKCLAW_TAILSCALE_AUTH_KEY", "").strip()


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
    """
    DuckDB a escanear para /goals --delta.

    Los fly commands (/goals) persisten en la bóveda del usuario (p. ej. quant_traderdb1.duckdb),
    mientras que get_gateway_db_path() suele apuntar al hub del tenant (p. ej. finanzdb1.duckdb).
    Sin multiplex, ambos pueden ser el mismo archivo; con Telegram multiplex suelen ser distintos.
    """
    raw = (os.getenv("DUCKCLAW_GOALS_TICKER_DB_PATH") or "").strip()
    if raw:
        from duckclaw.gateway_db import resolve_env_duckdb_path

        return [resolve_env_duckdb_path(raw)]

    seen: set[str] = set()
    out: List[str] = []

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
            db_path, now=now, headers=headers, scan_paths_n=len(scan_paths)
        )


async def _run_goals_proactive_tick_one_db(
    db_path: str,
    *,
    now: float,
    headers: Dict[str, str],
    scan_paths_n: int,
) -> None:
    try:
        with DuckClaw(db_path, read_only=True) as db_ro:
            raw = db_ro.query(
                "SELECT key, value FROM agent_config WHERE key LIKE 'chat_%_goals_delta_seconds'"
            )
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception as exc:  # noqa: BLE001
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

        with DuckClaw(db_path, read_only=True) as db:
            goals = get_manager_goals(db, chat_id)
            if not goals:
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

            tenant_id = (get_chat_state(db, chat_id, _GOALS_PROACTIVE_TENANT_KEY) or "").strip()
            worker_id = (get_chat_state(db, chat_id, "worker_id") or "").strip()
            if (not worker_id or worker_id.lower() == "manager") and tenant_id.lower() == "cuantitativo":
                worker_id = "Quant-Trader"
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
                if session_uid:
                    try:
                        raw_sess = db.query(
                            "SELECT mode, tickers, session_goal, session_uid, status "
                            "FROM quant_core.trading_sessions WHERE id = 'active' LIMIT 1"
                        )
                        sess_rows = json.loads(raw_sess) if isinstance(raw_sess, str) else (raw_sess or [])
                        if sess_rows and isinstance(sess_rows[0], dict):
                            row = sess_rows[0]
                            if str(row.get("status") or "").strip().upper() != "ACTIVE":
                                message = "[SYSTEM_EVENT: No hay sesión activa. Tick cancelado.]"
                            else:
                                mode = str(row.get("mode") or "paper").strip().lower() or "paper"
                                tickers_csv = str(row.get("tickers") or "").strip()
                                if tickers_csv:
                                    tickers = [x.strip().upper() for x in tickers_csv.split(",") if x.strip()]
                                goal_raw = row.get("session_goal")
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
                                session_uid = str(row.get("session_uid") or session_uid).strip()
                                message = build_trading_tick_system_event_message(
                                    session_uid=session_uid,
                                    tickers=tickers,
                                    mode=mode,
                                    signal_threshold=signal_threshold,
                                )
                        else:
                            message = "[SYSTEM_EVENT: No hay sesión activa. Tick cancelado.]"
                    except Exception:
                        message = "[SYSTEM_EVENT: No se pudo resolver la sesión activa. Tick cancelado.]"
                else:
                    message = "[SYSTEM_EVENT: No hay session_uid en goals_delta_meta. Tick cancelado.]"
            else:
                message = build_goals_proactive_system_event_message(goals)

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
        url = _agent_chat_url_for_worker(GATEWAY_URL, worker_id)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    params={"tenant_id": tenant_id, "deliver_outbound": "1"},
                    json=payload,
                    headers=headers,
                    timeout=120.0,
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
                    _m_curr = re.search(r"PnL no realizado=\$([\-0-9,]+(?:\.[0-9]+)?)", _resp_text)
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


async def run_heartbeat() -> None:
    r = redis.from_url(REDIS_URL)
    interval = float(HEARTBEAT_INTERVAL_SECONDS)
    poll = max(5, GOALS_TICKER_POLL_SECONDS)
    # Primer ciclo debe poder evaluar homeostasis de inmediato (antes: evaluar y luego sleep).
    last_homeo = time.time() - interval

    while True:
        try:
            await _run_goals_proactive_tick()
        except Exception as exc:  # noqa: BLE001
            logger.exception("goals_proactive: ciclo: %s", exc)

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
