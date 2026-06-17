from __future__ import annotations

"""
DuckClaw Heartbeat Daemon

Bucle asíncrono que evalúa homeostasis periódicamente y, cuando detecta anomalías,
inyecta un pensamiento interno ([SYSTEM_EVENT]) en el API Gateway.

Incluye un ticker de revisión /crons --delta (intervalo corto, independiente del
ciclo largo de homeostasis).
"""

import asyncio
import json
import logging
import os
import random
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
from duckclaw.homeostasis import BeliefRegistry, HomeostasisManager
from duckclaw.gateway_db import get_gateway_db_path, iter_goals_ticker_duckdb_paths
from duckclaw.runtime.scheduling.cron_wall_schedule import wall_once_expired, wall_schedule_should_fire
from duckclaw.commands.goals import get_manager_goals
from duckclaw.graphs.on_the_fly_commands import (
    _GOALS_CRON_WALL_KEY,
    _GOALS_DELTA_META_KEY,
    _GOALS_PROACTIVE_NOTIFY_KEY,
    _MEDITATE_DELTA_SECONDS_KEY,
    _MEDITATE_LAST_FIRE_KEY,
    _MEDITATE_TENANT_KEY,
    _MEDITATE_WORKER_KEY,
    _crons_debug_log,
    _GOALS_PROACTIVE_LAST_FIRE_KEY,
    _GOALS_PROACTIVE_TENANT_KEY,
    build_goals_proactive_system_event_message,
    chat_id_from_goals_cron_wall_key,
    chat_id_from_goals_delta_config_key,
    chat_id_from_meditate_delta_config_key,
    get_chat_state,
)
from harness_core.targets import get_manifest_goals_for_chat
from duckclaw.workers.factory import list_workers
from duckclaw.workers.manifest import load_manifest


logger = logging.getLogger("heartbeat")
logging.basicConfig(level=logging.INFO)


from duckclaw.env_config import resolve_agent_chat_url, resolve_redis_url

REDIS_URL = resolve_redis_url()
GATEWAY_URL = resolve_agent_chat_url()
HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "3600"))
GOALS_TICKER_POLL_SECONDS = int(os.getenv("GOALS_TICKER_POLL_SECONDS", "45"))
MEDITATE_DEFAULT_DELTA_SECONDS = int(os.getenv("MEDITATE_DELTA_SECONDS", "14400"))
GITHUB_MCP_HEALTH_SECONDS = float(os.getenv("DUCKCLAW_GITHUB_MCP_HEALTH_SECONDS", "300"))
_GITHUB_PAT_401_AUDIT_COOLDOWN_KEY = "duckclaw:heartbeat:github_pat_401_audit_v1"
# POST a /api/v1/agent/chat para jobs proactivos que pueden ejecutar varias tools.
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


async def check_alignment_nudge_cooldown(
    r: redis.Redis | None,
    tenant_id: str,
    chat_id: str,
    delta_s: int,
) -> bool:
    """True si se puede enviar nudge de alineación; si ok, fija cooldown."""
    if r is None:
        return True
    key = f"cooldown:{tenant_id}:{chat_id}:alignment_nudge"
    if await r.exists(key):
        return False
    ttl = max(60, min(int(delta_s), 14400))
    await r.setex(key, ttl, "locked")
    return True


async def _evaluate_homeostasis() -> List[Dict[str, Any]]:
    """
    Recorre workers con homeostasis_config y evalúa sus beliefs.

    Devuelve una lista de dicts con:
    - tenant_id: normalmente el schema/worker_id configurado en DB
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
    """Escanea agent_config y dispara SYSTEM_EVENT de revisión /crons cuando toca."""
    now = time.time()
    scan_paths = _goals_ticker_scan_db_paths()
    headers: Dict[str, str] = {}
    if TAILSCALE_AUTH_KEY:
        headers["X-Tailscale-Auth-Key"] = TAILSCALE_AUTH_KEY
    r_client: redis.Redis | None = None
    if REDIS_URL:
        try:
            r_client = redis.from_url(REDIS_URL)
        except Exception:
            r_client = None

    for db_path in scan_paths:
        await _run_goals_proactive_tick_one_db(
            db_path,
            now=now,
            headers=headers,
            scan_paths_n=len(scan_paths),
            redis_client=r_client,
        )


async def _run_goals_proactive_tick_one_db(
    db_path: str,
    *,
    now: float,
    headers: Dict[str, str],
    scan_paths_n: int,
    redis_client: redis.Redis | None = None,
) -> None:
    try:
        with duckclaw_open_for_read_scan(db_path) as db_ro:
            raw = db_ro.query(
                "SELECT key, value FROM agent_config WHERE key LIKE 'chat_%_goals_delta_seconds'"
            )
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
            raw_w = db_ro.query("SELECT key, value FROM agent_config WHERE key LIKE 'chat_%_goals_cron_wall'")
            wrows = json.loads(raw_w) if isinstance(raw_w, str) else (raw_w or [])
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

    if not rows and not (wrows or []):
        return

    for row in rows or []:
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
            tenant_id_pre = (get_chat_state(db, chat_id, _GOALS_PROACTIVE_TENANT_KEY) or "").strip()
            goals = get_manifest_goals_for_chat(db, chat_id, tenant_id=tenant_id_pre or None)
            if not goals:
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
            _wid_pre = (worker_id or "").strip()
            _gw_trigger = str(meta_pre.get("trigger") or "").strip().lower() == "goals_wall"
            allow_empty_goals = bool(not goals and _gw_trigger)
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
                        ("goals_cron_wall", ""),
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
                    "repite /crons --delta tras actualizar",
                    chat_id,
                )
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
            from duckclaw.homeostasis.goals_alignment import normalize_jitter_ratio

            jitter_ratio = normalize_jitter_ratio(meta.get("jitter_ratio"))
            effective_delta = float(delta_s) * (
                1.0 - jitter_ratio + 2.0 * jitter_ratio * random.random()
            )
            last_raw = (get_chat_state(db, chat_id, _GOALS_PROACTIVE_LAST_FIRE_KEY) or "").strip()
            try:
                last_fire = float(last_raw) if last_raw else 0.0
            except ValueError:
                last_fire = 0.0
            if last_fire > 0 and (now - last_fire) < effective_delta:
                continue
            notify_channel = ""
            message = ""
            from duckclaw.homeostasis.goals_alignment import (
                assess_goals_alignment,
                build_alignment_nudge_system_event,
                normalize_notify_channel,
                normalize_proactive_mode,
            )

            if "mode" in meta and str(meta.get("mode") or "").strip():
                proactive_mode = normalize_proactive_mode(str(meta.get("mode")))
            else:
                # Schedules legacy (pre GOALS_ALIGNMENT) y tests sin meta.mode: tick periódico.
                proactive_mode = "always"
            report = assess_goals_alignment(db, chat_id, worker_id=_wid_pre)
            notify_channel = normalize_notify_channel(
                get_chat_state(db, chat_id, _GOALS_PROACTIVE_NOTIFY_KEY)
            )
            if proactive_mode == "on_misalignment" and report.aligned:
                logger.debug(
                    "goals_proactive: alineado; omitiendo tick chat=%s mode=%s",
                    chat_id,
                    proactive_mode,
                )
                continue
            if not report.aligned:
                if not await check_alignment_nudge_cooldown(
                    redis_client, tenant_id or "default", str(chat_id), delta_s
                ):
                    logger.debug(
                        "goals_proactive: cooldown alineación chat=%s",
                        chat_id,
                    )
                    continue
                message = build_alignment_nudge_system_event(
                    report,
                    chat_id=str(chat_id),
                    epoch=now,
                )
            else:
                message = build_goals_proactive_system_event_message(goals)

            if not notify_channel:
                from duckclaw.homeostasis.goals_alignment import normalize_notify_channel

                notify_channel = normalize_notify_channel(
                    get_chat_state(db, chat_id, _GOALS_PROACTIVE_NOTIFY_KEY)
                )

        payload = {
            "message": message,
            "chat_id": str(chat_id),
            "user_id": str(chat_id),
            "username": "Usuario",
            "chat_type": "private",
            "tenant_id": tenant_id,
            "is_system_prompt": True,
            "skip_session_lock": True,
            "notify_channel": notify_channel,
        }
        url = _agent_chat_url_for_worker(GATEWAY_URL, worker_id)
        _crons_debug_log(
            "heartbeat/main.py:_run_goals_proactive_tick_one_db",
            "goals_proactive_http_post",
            {
                "chat_id": str(chat_id),
                "worker_id": worker_id,
                "db_path_tail": str(Path(db_path).name),
            },
            hypothesis_id="C",
        )
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
            _crons_debug_log(
                "heartbeat/main.py:_run_goals_proactive_tick_one_db",
                "goals_proactive_http_ok",
                {"chat_id": str(chat_id), "status_code": resp.status_code},
                hypothesis_id="C",
            )
            await _enqueue_chat_state_write(
                db_path=db_path,
                chat_id=chat_id,
                tenant_id=tenant_id or "default",
                key=_GOALS_PROACTIVE_LAST_FIRE_KEY,
                value=str(now),
            )
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

    wall_poll = float(GOALS_TICKER_POLL_SECONDS)
    for wrow in wrows or []:
        if not isinstance(wrow, dict):
            continue
        wkey = str(wrow.get("key") or "")
        chat_id_w = chat_id_from_goals_cron_wall_key(wkey)
        if not chat_id_w:
            continue
        wall_raw = str(wrow.get("value") or "").strip()
        if not wall_raw:
            continue
        try:
            wall_spec: Dict[str, Any] = json.loads(wall_raw)
        except Exception:
            continue
        if not isinstance(wall_spec, dict):
            continue

        with duckclaw_open_for_read_scan(db_path) as db_chk:
            try:
                ds_chk = int(str(get_chat_state(db_chk, chat_id_w, "goals_delta_seconds") or "0").strip() or "0")
            except ValueError:
                ds_chk = 0
        if ds_chk > 0:
            continue

        if wall_once_expired(wall_spec, now):
            try:
                await _enqueue_chat_state_write(
                    db_path=db_path,
                    chat_id=chat_id_w,
                    tenant_id="default",
                    key=_GOALS_CRON_WALL_KEY,
                    value="",
                )
            except Exception as _wexc:
                logger.debug("goals_proactive: limpiar wall expirado chat=%s: %s", chat_id_w, _wexc)
            continue

        with duckclaw_open_for_read_scan(db_path) as db:
            tenant_id_w = (get_chat_state(db, chat_id_w, _GOALS_PROACTIVE_TENANT_KEY) or "").strip()
            goals = get_manifest_goals_for_chat(db, chat_id_w, tenant_id=tenant_id_w or None)
            if not goals:
                goals = get_manager_goals(db, chat_id_w)
            meta_raw_pre = (get_chat_state(db, chat_id_w, _GOALS_DELTA_META_KEY) or "").strip()
            meta_pre: Dict[str, Any] = {}
            if meta_raw_pre:
                try:
                    _mp = json.loads(meta_raw_pre)
                    if isinstance(_mp, dict):
                        meta_pre = _mp
                except Exception:
                    meta_pre = {}
            tenant_id = (get_chat_state(db, chat_id_w, _GOALS_PROACTIVE_TENANT_KEY) or "").strip()
            worker_id = (get_chat_state(db, chat_id_w, "worker_id") or "").strip()
            _gw_trigger = str(meta_pre.get("trigger") or "").strip().lower() == "goals_wall"
            allow_empty_goals = bool(not goals and _gw_trigger)
            if not goals and not allow_empty_goals:
                logger.info("goals_proactive: chat=%s sin goals; limpiando wall", chat_id_w)
                try:
                    await _enqueue_chat_state_write(
                        db_path=db_path,
                        chat_id=chat_id_w,
                        tenant_id="default",
                        key=_GOALS_CRON_WALL_KEY,
                        value="",
                    )
                except Exception as _exc:
                    logger.warning("goals_proactive: error al limpiar wall chat=%s: %s", chat_id_w, _exc)
                continue

            if not worker_id or worker_id.lower() == "manager":
                logger.debug(
                    "goals_proactive_wall: omitiendo chat=%s (worker_id=%r tenant_id=%r)",
                    chat_id_w,
                    worker_id,
                    tenant_id,
                )
                continue

            if not tenant_id:
                logger.warning(
                    "goals_proactive_wall: chat=%s sin goals_proactive_tenant_id",
                    chat_id_w,
                )
                continue

            last_raw = (get_chat_state(db, chat_id_w, _GOALS_PROACTIVE_LAST_FIRE_KEY) or "").strip()
            try:
                last_fire = float(last_raw) if last_raw else 0.0
            except ValueError:
                last_fire = 0.0
            if not wall_schedule_should_fire(now, wall_spec, last_fire, wall_poll):
                continue
            meta_raw = (get_chat_state(db, chat_id_w, _GOALS_DELTA_META_KEY) or "").strip()
            meta: Dict[str, Any] = {}
            if meta_raw:
                try:
                    maybe_meta = json.loads(meta_raw)
                    if isinstance(maybe_meta, dict):
                        meta = maybe_meta
                except Exception:
                    meta = {}
            message = build_goals_proactive_system_event_message(goals)

        chat_id = chat_id_w
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
                    timeout=_GOALS_PROACTIVE_HTTP_TIMEOUT,
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "goals_proactive_wall: error HTTP chat=%s worker=%s: %s",
                chat_id,
                worker_id,
                exc,
            )
            continue

        if 200 <= resp.status_code < 300:
            await _enqueue_chat_state_write(
                db_path=db_path,
                chat_id=chat_id,
                tenant_id=tenant_id or "default",
                key=_GOALS_PROACTIVE_LAST_FIRE_KEY,
                value=str(now),
            )
            if str(wall_spec.get("kind") or "").strip().lower() == "once":
                try:
                    await _enqueue_chat_state_write(
                        db_path=db_path,
                        chat_id=chat_id,
                        tenant_id=tenant_id or "default",
                        key=_GOALS_CRON_WALL_KEY,
                        value="",
                    )
                except Exception as _oce:
                    logger.debug("goals_proactive_wall: limpiar once chat=%s: %s", chat_id, _oce)
            logger.info(
                "goals_proactive_wall: tick OK chat=%s worker=%s",
                chat_id,
                worker_id,
            )
        else:
            logger.warning(
                "goals_proactive_wall: HTTP %s chat=%s body=%s",
                resp.status_code,
                chat_id,
                (resp.text or "")[:200],
            )


async def _run_meditate_proactive_tick() -> None:
    """Escanea agent_config y dispara meditate_graph cuando toca (infra, sin SYSTEM_EVENT)."""
    now = time.time()
    scan_paths = _goals_ticker_scan_db_paths()
    for db_path in scan_paths:
        await _run_meditate_proactive_tick_one_db(db_path, now=now)


async def _run_meditate_proactive_tick_one_db(db_path: str, *, now: float) -> None:
    try:
        with duckclaw_open_for_read_scan(db_path) as db_ro:
            raw = db_ro.query(
                "SELECT key, value FROM agent_config WHERE key LIKE 'chat_%_meditate_delta_seconds'"
            )
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception as exc:  # noqa: BLE001
        if _goals_proactive_db_open_error_is_expected(exc):
            logger.debug("meditate_proactive: omitiendo %s: %s", db_path, exc)
        else:
            logger.warning("meditate_proactive: no se pudo leer agent_config (%s): %s", db_path, exc)
        return

    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "")
        chat_id = chat_id_from_meditate_delta_config_key(key)
        if not chat_id:
            continue
        try:
            delta_s = int(str(row.get("value") or "0").strip() or "0")
        except ValueError:
            continue
        if delta_s <= 0:
            continue

        with duckclaw_open_for_read_scan(db_path) as db:
            tenant_id = (get_chat_state(db, chat_id, _MEDITATE_TENANT_KEY) or "").strip()
            worker_id = (get_chat_state(db, chat_id, _MEDITATE_WORKER_KEY) or "").strip()
            if not worker_id:
                worker_id = (get_chat_state(db, chat_id, "worker_id") or "").strip()
            if not tenant_id:
                tenant_id = (get_chat_state(db, chat_id, "tenant_id") or "default").strip() or "default"
            if not worker_id or worker_id.lower() == "manager":
                logger.debug("meditate_proactive: omitiendo chat=%s sin worker", chat_id)
                continue
            last_raw = (get_chat_state(db, chat_id, _MEDITATE_LAST_FIRE_KEY) or "").strip()
            try:
                last_fire = float(last_raw) if last_raw else 0.0
            except ValueError:
                last_fire = 0.0
            if last_fire > 0 and (now - last_fire) < float(delta_s):
                continue

        def _meditate_tick_sync() -> dict:
            from duckclaw.graphs.on_the_fly_commands import invoke_meditate_cycle_for_chat

            with duckclaw_open_for_read_scan(db_path) as db_sync:
                tid = tenant_id or (
                    get_chat_state(db_sync, chat_id, "tenant_id") or "default"
                ).strip() or "default"
                return invoke_meditate_cycle_for_chat(
                    db_sync,
                    chat_id,
                    tenant_id=tid,
                    worker_id=worker_id,
                    delta_s=delta_s,
                )

        try:
            result = await asyncio.to_thread(_meditate_tick_sync)
            status = str((result or {}).get("status") or "")
            if status == "failed":
                logger.warning(
                    "meditate_proactive: run failed chat=%s err=%s",
                    chat_id,
                    (result or {}).get("error"),
                )
            else:
                logger.info("meditate_proactive: tick OK chat=%s worker=%s", chat_id, worker_id)
                try:
                    from duckclaw.graphs.on_the_fly_commands import _publish_meditate_tick_heartbeat

                    _publish_meditate_tick_heartbeat(
                        chat_id,
                        tenant_id=tenant_id,
                        worker_id=worker_id,
                        cycle=result if isinstance(result, dict) else None,
                    )
                except Exception:
                    pass
            await _enqueue_chat_state_write(
                db_path=db_path,
                chat_id=chat_id,
                tenant_id=tenant_id,
                key=_MEDITATE_LAST_FIRE_KEY,
                value=str(now),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("meditate_proactive: invoke failed chat=%s: %s", chat_id, exc)


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

        try:
            await _run_meditate_proactive_tick()
        except Exception as exc:  # noqa: BLE001
            logger.exception("meditate_proactive: ciclo: %s", exc)

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
                                params={"tenant_id": tenant_id},
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
