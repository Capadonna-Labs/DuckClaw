"""Cognitive /loop scheduling: auto-mejora LLM vs manifiesto /goals (formerly /meditate)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional, Protocol
from urllib.parse import quote

_log = logging.getLogger(__name__)

from duckclaw.commands.chat_state import (
    _PREFIX,
    _skip_runtime_ddl,
    get_chat_state,
    set_chat_state,
    set_chat_state_via_typed_command,
)
from duckclaw.commands.crons import (
    clear_interval_schedule_only,
    format_goals_delta_interval_human,
    parse_goals_delta_arg,
)

from duckclaw.commands.loop_state_keys import (
    LOOP_ACTIVE_KEY,
    LOOP_AWAITING_USER_KEY,
    LOOP_DELTA_IDLE_KEY,
    LOOP_DELTA_SECONDS_KEY,
    LOOP_LAST_ACTIVITY_KEY,
    LOOP_LAST_FIRE_KEY,
    LOOP_PENDING_TICK_KEY,
    LOOP_TENANT_KEY,
    LOOP_WORKER_KEY,
    get_loop_chat_state,
    migrate_loop_chat_state_keys,
    persist_loop_chat_state,
)
from duckclaw.commands.history import _infer_user_id_for_audit_queue

LOOP_DELTA_MIN_SECONDS = 60
LOOP_DELTA_MAX_SECONDS = 7 * 24 * 3600
LOOP_SELF_HTTP_TIMEOUT = float(os.environ.get("DUCKCLAW_GOALS_PROACTIVE_HTTP_TIMEOUT", "300"))
# Legacy /loop on 4h (Heartbeat reloj). /loop on sin args = turnos agent↔user.
LOOP_DEFAULT_INTERVAL_SECONDS = 15 * 60
LOOP_SYSTEM_USER_LABEL = "[Ciclo loop]"


def is_loop_status_fly_text(*texts: str) -> bool:
    """True si el turno es solo ``/loop --status`` (no ancla inactividad ni turno)."""
    from duckclaw.graphs.on_the_fly_commands import parse_command

    for raw in texts:
        chunk = (raw or "").strip()
        if not chunk.startswith("/"):
            continue
        line = chunk.split("\n", 1)[0].strip()
        name, args = parse_command(line)
        if name not in ("loop", "meditate"):
            continue
        if _parse_loop_args(args or "").get("action") == "status":
            return True
    return False


def _resolve_loop_worker_id(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str,
    entry_worker_id: str | None = None,
) -> str:
    """Worker efectivo: agent_config del chat, o entry_worker del playground."""
    worker_id = (get_chat_state(db, chat_id, "worker_id") or "").strip()
    if worker_id and worker_id.lower() != "manager":
        return worker_id
    ew = (entry_worker_id or "").strip()
    if not ew or ew.lower() == "manager":
        return ""
    try:
        from duckclaw.commands.team_templates import _resolve_template_id
        from duckclaw.workers.discovery import list_workers_for_fly

        canonical = _resolve_template_id(list_workers_for_fly(tenant_id=tenant_id), ew)
        return canonical or ew
    except Exception:
        return ew


class LoopTickHeartbeatPublisher(Protocol):
    def publish_loop_tick(
        self,
        chat_id: Any,
        *,
        tenant_id: str,
        worker_id: str,
        summary: str,
    ) -> None: ...


_loop_tick_heartbeat_publisher: LoopTickHeartbeatPublisher | None = None


def configure_loop_tick_heartbeat_publisher(
    publisher: LoopTickHeartbeatPublisher | None,
) -> None:
    """Inject admin UI heartbeat publisher from the graph facade."""
    global _loop_tick_heartbeat_publisher
    _loop_tick_heartbeat_publisher = publisher


def parse_loop_delta_arg(fragment: str) -> tuple[Optional[int], Optional[str]]:
    """Alias de parse_goals_delta_arg con mismos límites de intervalo."""
    return parse_goals_delta_arg(fragment)


def chat_id_from_loop_delta_config_key(key: str) -> Optional[str]:
    """Extrae chat_id desde fila agent_config con sufijo _loop_delta_seconds."""
    suf = f"_{LOOP_DELTA_SECONDS_KEY}"
    if not key.startswith(_PREFIX) or not key.endswith(suf):
        return None
    return key[len(_PREFIX) : -len(suf)] or None


def agent_chat_url_for_worker(gateway_url: str, worker_id: str) -> str:
    base = gateway_url.rstrip("/").rsplit("/", 1)[0]
    return f"{base}/{quote(worker_id, safe='')}/chat?deliver_outbound=1"


def _goal_title_for_event(goal: dict[str, Any], fallback_key: str = "") -> str:
    from harness_core.goal_priority import goal_priority_label

    t = (goal.get("title") or "").strip()
    if t:
        title = t[:80] + ("…" if len(t) > 80 else "")
    else:
        title = (goal.get("belief_key") or fallback_key or "").strip()
    pl = goal_priority_label(goal)
    return f"{pl} {title}" if pl else title


def is_loop_active_mode(db: Any, chat_id: Any) -> bool:
    """True si /loop on (modo conversación por turnos) está activo."""
    migrate_loop_chat_state_keys(db, chat_id)
    return (get_loop_chat_state(db, chat_id, LOOP_ACTIVE_KEY) or "").strip() == "1"


def is_loop_awaiting_user(db: Any, chat_id: Any) -> bool:
    """True si el agente ya habló y espera el próximo mensaje del usuario."""
    return (get_loop_chat_state(db, chat_id, LOOP_AWAITING_USER_KEY) or "").strip() == "1"


def is_loop_delta_idle_mode(db: Any, chat_id: Any) -> bool:
    """True si /loop --delta (inactividad desde último mensaje) está activo."""
    migrate_loop_chat_state_keys(db, chat_id)
    return (get_loop_chat_state(db, chat_id, LOOP_DELTA_IDLE_KEY) or "").strip() == "1"


def get_loop_last_activity_epoch(db: Any, chat_id: Any) -> float:
    """Epoch del último mensaje usuario o agente persistido en el chat."""
    migrate_loop_chat_state_keys(db, chat_id)
    raw = (get_loop_chat_state(db, chat_id, LOOP_LAST_ACTIVITY_KEY) or "").strip()
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def touch_loop_last_activity(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str = "default",
    ts: float | None = None,
) -> None:
    """Ancla inactividad /loop --delta al último mensaje visible."""
    tid = str(tenant_id or "default").strip() or "default"
    epoch = time.time() if ts is None else float(ts)
    _persist_loop_chat_state(
        db, chat_id, LOOP_LAST_ACTIVITY_KEY, str(epoch), tenant_id=tid
    )
    _persist_loop_chat_state(db, chat_id, LOOP_PENDING_TICK_KEY, "0", tenant_id=tid)


def set_loop_awaiting_user(
    db: Any,
    chat_id: Any,
    awaiting: bool,
    *,
    tenant_id: str = "default",
) -> None:
    tid = str(tenant_id or "default").strip() or "default"
    _persist_loop_chat_state(
        db,
        chat_id,
        LOOP_AWAITING_USER_KEY,
        "1" if awaiting else "0",
        tenant_id=tid,
    )


def enable_loop_active_mode(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str,
    worker_id: str,
    idle_interval_seconds: int = 0,
) -> dict[str, Any]:
    """Activa modo conversación por turnos; opcional timeout --delta idle."""
    tid = str(tenant_id or "default").strip() or "default"
    wid = (worker_id or "").strip()
    if not wid or wid.lower() == "manager":
        return {"status": "error", "error": "worker_id missing or manager"}
    idle_secs = int(idle_interval_seconds or 0)
    if idle_secs > 0:
        idle_secs = max(LOOP_DELTA_MIN_SECONDS, min(idle_secs, LOOP_DELTA_MAX_SECONDS))
    pairs: list[tuple[str, str]] = [
        (LOOP_ACTIVE_KEY, "1"),
        (LOOP_AWAITING_USER_KEY, "0"),
        (LOOP_TENANT_KEY, tid),
        (LOOP_WORKER_KEY, wid),
        (LOOP_LAST_FIRE_KEY, ""),
    ]
    if idle_secs > 0:
        pairs.extend(
            [
                (LOOP_DELTA_SECONDS_KEY, str(idle_secs)),
                (LOOP_DELTA_IDLE_KEY, "1"),
            ]
        )
        if get_loop_last_activity_epoch(db, chat_id) <= 0:
            touch_loop_last_activity(db, chat_id, tenant_id=tid)
    else:
        pairs.extend(
            [
                (LOOP_DELTA_SECONDS_KEY, "0"),
                (LOOP_DELTA_IDLE_KEY, "0"),
            ]
        )
    for k, v in pairs:
        ok, err = _persist_loop_chat_state(db, chat_id, k, v, tenant_id=tid)
        if not ok:
            return {"status": "error", "error": err or f"persist failed: {k}"}
    return {
        "status": "ok",
        "enabled": True,
        "mode": "turn_based",
        "worker_id": wid,
        "tenant_id": tid,
        "idle_interval_seconds": idle_secs if idle_secs > 0 else None,
    }


def build_loop_active_user_continuation(
    db: Any,
    chat_id: Any,
    tenant_id: str,
    user_text: str,
) -> str:
    """Envuelve mensaje usuario en modo activo (siguiente turno discreto)."""
    from harness_core.targets import load_homeostasis_manifest, manifest_goals_as_dicts

    tid = str(tenant_id or "default").strip() or "default"
    manifest = load_homeostasis_manifest(db, tid, chat_id=chat_id)
    goals = manifest_goals_as_dicts(manifest)
    titles: list[str] = []
    for goal in goals:
        if not isinstance(goal, dict):
            continue
        key = (goal.get("belief_key") or "").strip()
        titles.append(_goal_title_for_event(goal, key))
    summary = "; ".join(titles[:12]) if titles else "(sin metas; usa /goals)"
    body = (user_text or "").strip()
    return (
        f"[SYSTEM_EVENT: Modo /loop activo (turno usuario→agente). Metas (/goals): {summary}. "
        "Contrasta con evaluate_homeostasis / assess_crons_alignment. "
        "Responde en el chat; si alineado → request_homeostasis_validation y pide /loop-approve. "
        "Si no, planifica y pregunta. ESPERA la siguiente respuesta del usuario — no solapes turnos. "
        "Modo sigue hasta /loop-approve u /loop off.]\n\n"
        f"{body}"
    )


def build_loop_self_system_event_message(
    db: Any,
    chat_id: Any,
    tenant_id: str,
    *,
    scheduled: bool = False,
    active_mode: bool | None = None,
) -> str:
    """SYSTEM_EVENT: auto-mejora cognitiva vs manifiesto /goals."""
    from harness_core.targets import load_homeostasis_manifest, manifest_goals_as_dicts

    manifest = load_homeostasis_manifest(db, tenant_id, chat_id=chat_id)
    goals = manifest_goals_as_dicts(manifest)
    titles: list[str] = []
    for goal in goals:
        if not isinstance(goal, dict):
            continue
        key = (goal.get("belief_key") or "").strip()
        titles.append(_goal_title_for_event(goal, key))
    summary = "; ".join(titles[:12]) if titles else "(sin metas; usa /goals)"
    active = (
        bool(active_mode)
        if active_mode is not None
        else is_loop_active_mode(db, chat_id)
    )
    if active:
        trigger = "modo conversación activa /loop on"
    elif scheduled:
        trigger = "programado /loop"
    else:
        trigger = "/loop"
    hitl_prefix = ""
    try:
        from duckclaw.hitl.loop_validation_service import get_pending_validation

        pending = get_pending_validation(db, chat_id)
        if pending:
            vid = str(pending.get("validation_id") or "")
            hitl_prefix = (
                f"Validación HITL pendiente (validation_id={vid}). "
                f"Prioriza recordar /loop-approve {vid} o /loop-reject. "
            )
    except Exception:
        pass
    wait_note = ""
    if active:
        wait_note = (
            " Tras tu respuesta, DETENTE y ESPERA el mensaje del usuario "
            "(turnos discretos agent↔user; no solapes ni ticks de reloj). "
            "El modo sigue hasta /loop-approve u /loop off."
        )
    priority_note = ""
    if len(goals) > 1:
        priority_note = (
            " Atiende metas en orden de prioridad (P1 antes que P2; menor número primero). "
        )
    return (
        f"[SYSTEM_EVENT: {hitl_prefix}Ciclo de auto-mejora {trigger}. Metas (/goals): {summary}.{priority_note} "
        "1) Usa assess_crons_alignment (o evaluate_homeostasis si tu worker la expone) "
        "y reporta el contraste en el chat. "
        "2) Si métricas alineadas (sin desviaciones), llama request_homeostasis_validation "
        "y DETENTE — pregunta confirmación HITL; no declares homeostasis hasta /loop-approve. "
        "3) Si hay desviaciones, planifica corrección con las tools de este worker y pregunta. "
        f"Metas solo vía /goals o manage_homeostasis_goals.{wait_note}]"
    )


def loop_repetition_interval_human(db: Any, chat_id: Any) -> tuple[str, bool]:
    """Intervalo humano y si está programado en agent_config."""
    status = get_loop_schedule_status(db, chat_id)
    if status.get("enabled"):
        secs = int(status.get("interval_seconds") or 0)
        human = status.get("interval_human") or format_goals_delta_interval_human(secs)
        return human, True
    return format_goals_delta_interval_human(LOOP_DEFAULT_INTERVAL_SECONDS), False


def _normalize_admin_chat_id(chat_id: Any) -> str:
    cid = str(chat_id or "").strip()
    if not cid:
        return cid
    try:
        from duckclaw.graphs.chat_heartbeat import admin_report_chat_id, is_admin_ui_chat_session

        if is_admin_ui_chat_session(cid):
            return admin_report_chat_id(cid) or cid
    except Exception:
        pass
    return cid


def _build_loop_tick_payload(
    *,
    chat_id: Any,
    tenant_id: str,
    message: str,
    vault_db_path: str | None = None,
) -> dict[str, Any]:
    cid = _normalize_admin_chat_id(chat_id)
    tid = str(tenant_id or "default").strip() or "default"
    payload: dict[str, Any] = {
        "message": message,
        "chat_id": cid,
        "user_id": cid,
        "username": "Usuario",
        "chat_type": "private",
        "tenant_id": tid,
        "is_system_prompt": True,
        "skip_session_lock": True,
    }
    vpath = (vault_db_path or "").strip()
    if vpath:
        payload["vault_db_path"] = vpath
    try:
        from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

        if is_admin_ui_chat_session(cid):
            payload["notify_channel"] = "admin"
            payload["user_incoming"] = LOOP_SYSTEM_USER_LABEL
    except Exception:
        pass
    return payload


def post_loop_self_tick_sync(
    *,
    chat_id: Any,
    tenant_id: str,
    worker_id: str,
    message: str,
    headers: dict[str, str] | None = None,
    vault_db_path: str | None = None,
) -> dict[str, Any]:
    """POST sync al gateway para disparar un turno meditate (fly o heartbeat sync path)."""
    import httpx

    from duckclaw.env_config import resolve_agent_chat_url

    tid = str(tenant_id or "default").strip() or "default"
    wid = str(worker_id or "").strip()
    url = agent_chat_url_for_worker(resolve_agent_chat_url(), wid)
    payload = _build_loop_tick_payload(
        chat_id=chat_id,
        tenant_id=tid,
        message=message,
        vault_db_path=vault_db_path,
    )
    hdrs = dict(headers or {})
    try:
        with httpx.Client(timeout=LOOP_SELF_HTTP_TIMEOUT) as client:
            resp = client.post(
                url,
                params={"tenant_id": tid, "deliver_outbound": "1"},
                json=payload,
                headers=hdrs,
            )
        ok = 200 <= resp.status_code < 300
        return {
            "ok": ok,
            "status_code": resp.status_code,
            "body": (resp.text or "")[:500],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def dispatch_loop_self_tick(
    *,
    chat_id: Any,
    tenant_id: str,
    worker_id: str,
    message: str,
    headers: dict[str, str] | None = None,
    vault_db_path: str | None = None,
    wait: bool = False,
) -> dict[str, Any]:
    """
    Dispara SYSTEM_EVENT meditate al gateway.

    Por defecto fire-and-forget en hilo daemon: el fly handler no debe bloquear
    300s ni hacer HTTP sync al mismo proceso Gateway (deadlock asyncio).
    """
    kwargs = {
        "chat_id": chat_id,
        "tenant_id": tenant_id,
        "worker_id": worker_id,
        "message": message,
        "headers": headers,
        "vault_db_path": vault_db_path,
    }
    if wait:
        return post_loop_self_tick_sync(**kwargs)

    def _run() -> None:
        result = post_loop_self_tick_sync(**kwargs)
        if not result.get("ok"):
            _log.warning(
                "loop self tick background failed chat=%s worker=%s: %s",
                chat_id,
                worker_id,
                result.get("error") or result.get("body") or result.get("status_code"),
            )

    threading.Thread(
        target=_run,
        name=f"loop-tick-{chat_id}",
        daemon=True,
    ).start()
    return {"ok": True, "status_code": 202, "dispatched": True}


async def post_loop_self_tick_async(
    *,
    chat_id: Any,
    tenant_id: str,
    worker_id: str,
    message: str,
    headers: dict[str, str] | None = None,
    vault_db_path: str | None = None,
) -> dict[str, Any]:
    """POST async al gateway (Heartbeat ticker)."""
    import httpx

    from duckclaw.env_config import resolve_agent_chat_url

    tid = str(tenant_id or "default").strip() or "default"
    wid = str(worker_id or "").strip()
    url = agent_chat_url_for_worker(resolve_agent_chat_url(), wid)
    payload = _build_loop_tick_payload(
        chat_id=chat_id,
        tenant_id=tid,
        message=message,
        vault_db_path=vault_db_path,
    )
    hdrs = dict(headers or {})
    try:
        async with httpx.AsyncClient(timeout=LOOP_SELF_HTTP_TIMEOUT) as client:
            resp = await client.post(
                url,
                params={"tenant_id": tid, "deliver_outbound": "1"},
                json=payload,
                headers=hdrs,
            )
        ok = 200 <= resp.status_code < 300
        return {
            "ok": ok,
            "status_code": resp.status_code,
            "body": (resp.text or "")[:500],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _persist_loop_chat_state(
    db: Any,
    chat_id: Any,
    key_suffix: str,
    value: str,
    *,
    tenant_id: str = "default",
) -> tuple[bool, str]:
    tid = str(tenant_id or "default").strip() or "default"
    return persist_loop_chat_state(db, chat_id, key_suffix, value, tenant_id=tid)


def clear_loop_schedule(db: Any, chat_id: Any, *, tenant_id: str = "default") -> None:
    """Desactiva programación por reloj, inactividad y modo activo por turnos."""
    tid = str(tenant_id or "default").strip() or "default"
    for k, v in (
        (LOOP_DELTA_SECONDS_KEY, "0"),
        (LOOP_DELTA_IDLE_KEY, "0"),
        (LOOP_LAST_FIRE_KEY, ""),
        (LOOP_LAST_ACTIVITY_KEY, ""),
        (LOOP_PENDING_TICK_KEY, "0"),
        (LOOP_TENANT_KEY, ""),
        (LOOP_WORKER_KEY, ""),
        (LOOP_ACTIVE_KEY, "0"),
        (LOOP_AWAITING_USER_KEY, "0"),
    ):
        _persist_loop_chat_state(db, chat_id, k, v, tenant_id=tid)


def clear_loop_delta_only(db: Any, chat_id: Any, *, tenant_id: str = "default") -> None:
    """Quita solo /loop --delta; conserva modo activo por turnos si estaba on."""
    tid = str(tenant_id or "default").strip() or "default"
    for k, v in (
        (LOOP_DELTA_SECONDS_KEY, "0"),
        (LOOP_DELTA_IDLE_KEY, "0"),
        (LOOP_LAST_FIRE_KEY, ""),
        (LOOP_LAST_ACTIVITY_KEY, ""),
        (LOOP_PENDING_TICK_KEY, "0"),
    ):
        _persist_loop_chat_state(db, chat_id, k, v, tenant_id=tid)


_LOOP_OFF_REMOTE_SUFFIXES: dict[str, str] = {
    LOOP_DELTA_SECONDS_KEY: "0",
    LOOP_DELTA_IDLE_KEY: "0",
    LOOP_LAST_FIRE_KEY: "",
    LOOP_LAST_ACTIVITY_KEY: "",
    LOOP_PENDING_TICK_KEY: "0",
    LOOP_TENANT_KEY: "",
    LOOP_WORKER_KEY: "",
    LOOP_ACTIVE_KEY: "0",
    LOOP_AWAITING_USER_KEY: "0",
    "meditate_delta_seconds": "0",
    "meditate_active": "0",
    "meditate_awaiting_user": "0",
    "meditate_last_fire_epoch": "",
    "meditate_tenant_id": "",
    "meditate_worker_id": "",
}

_GOALS_INTERVAL_OFF_REMOTE_SUFFIXES: dict[str, str] = {
    "goals_delta_seconds": "0",
    "goals_proactive_anchor": "",
    "goals_delta_anchor": "",
    "goals_delta_meta": "",
    "goals_proactive_notify": "",
}


def clear_loop_schedule_all_dbs(db: Any, chat_id: Any, *, tenant_id: str = "default") -> None:
    """Apaga /loop y revisión /crons --delta en fly_db y en todas las bóvedas del ticker."""
    from duckclaw.commands.crons import _enqueue_agent_config_entries_remote
    from duckclaw.gateway_db import iter_goals_ticker_duckdb_paths

    tid = str(tenant_id or "default").strip() or "default"
    clear_loop_schedule(db, chat_id, tenant_id=tid)
    clear_interval_schedule_only(db, chat_id, tenant_id=tid)

    primary_resolved = ""
    try:
        raw_p = str(getattr(db, "_path", "") or "").strip()
        if raw_p:
            primary_resolved = str(Path(raw_p).expanduser().resolve())
    except Exception:
        primary_resolved = str(getattr(db, "_path", "") or "").strip()

    for db_path in iter_goals_ticker_duckdb_paths():
        rp = ""
        try:
            rp = str(Path(db_path).expanduser().resolve())
        except OSError:
            rp = str(db_path)
        if primary_resolved and rp == primary_resolved:
            continue
        try:
            _enqueue_agent_config_entries_remote(db_path, chat_id, _LOOP_OFF_REMOTE_SUFFIXES)
            _enqueue_agent_config_entries_remote(
                db_path, chat_id, _GOALS_INTERVAL_OFF_REMOTE_SUFFIXES
            )
        except Exception:
            pass


def get_loop_schedule_status(db: Any, chat_id: Any) -> dict[str, Any]:
    """Estado del programador meditate cognitivo para este chat."""
    try:
        secs = int((get_loop_chat_state(db, chat_id, LOOP_DELTA_SECONDS_KEY) or "0").strip() or "0")
    except ValueError:
        secs = 0
    active = is_loop_active_mode(db, chat_id)
    idle_mode = is_loop_delta_idle_mode(db, chat_id)
    last_activity = get_loop_last_activity_epoch(db, chat_id)
    return {
        "enabled": secs > 0 or active,
        "active_mode": active,
        "delta_idle_mode": idle_mode,
        "awaiting_user": is_loop_awaiting_user(db, chat_id),
        "interval_seconds": secs,
        "interval_human": format_goals_delta_interval_human(secs) if secs > 0 else None,
        "tenant_id": (get_loop_chat_state(db, chat_id, LOOP_TENANT_KEY) or "").strip() or None,
        "worker_id": (get_loop_chat_state(db, chat_id, LOOP_WORKER_KEY) or "").strip() or None,
        "last_fire_epoch": (get_loop_chat_state(db, chat_id, LOOP_LAST_FIRE_KEY) or "").strip() or None,
        "last_activity_epoch": str(last_activity) if last_activity > 0 else None,
    }


def format_loop_next_tick_footer(db: Any, chat_id: Any, *, now: float | None = None) -> str:
    """Pie de respuesta: modo turnos, inactividad --delta o reloj legacy."""
    status = get_loop_schedule_status(db, chat_id)
    ts = time.time() if now is None else float(now)
    from datetime import datetime
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("America/Bogota")
    secs = int(status.get("interval_seconds") or 0)
    human_interval = status.get("interval_human") or format_goals_delta_interval_human(secs)
    idle_mode = bool(status.get("delta_idle_mode"))

    if status.get("active_mode"):
        if idle_mode and secs > 0:
            last_act = get_loop_last_activity_epoch(db, chat_id)
            if last_act > 0:
                try:
                    next_epoch = last_act + secs
                    remaining = max(0, int(next_epoch - ts))
                    clock = datetime.fromtimestamp(next_epoch, tz=tz).strftime("%H:%M")
                    remain_h = (
                        format_goals_delta_interval_human(remaining)
                        if remaining > 0
                        else "< 1 min"
                    )
                    overdue = (not status.get("awaiting_user")) and next_epoch <= ts
                    if overdue and remaining == 0:
                        overdue_min = max(1, int((ts - next_epoch) // 60))
                        return (
                            f"\n\n⏭️ **Modo /loop activo** — timeout vencido hace ~{overdue_min} min "
                            f"(debía ~{clock} COT). Heartbeat reintentará el ciclo; "
                            f"`/loop --now` fuerza ya. `/loop off` para detener."
                        )
                    if status.get("awaiting_user"):
                        return (
                            f"\n\n⏭️ **Modo /loop activo** — esperando tu respuesta; "
                            f"si no respondes, próximo ciclo ~{clock} COT "
                            f"(silencio ~{remain_h} · timeout {human_interval}). "
                            "`/loop off` para detener."
                        )
                    return (
                        f"\n\n⏭️ **Modo /loop activo** — ciclo en curso; próximo ciclo ~{clock} COT "
                        f"(silencio ~{remain_h} · timeout {human_interval}). `/loop off` para detener."
                    )
                except (TypeError, ValueError, OverflowError, OSError):
                    pass
            try:
                next_epoch = ts + secs
                clock = datetime.fromtimestamp(next_epoch, tz=tz).strftime("%H:%M")
                return (
                    f"\n\n⏭️ **Modo /loop activo** — próximo ciclo ~{clock} COT "
                    f"(en ~{human_interval} · timeout {human_interval}). `/loop off` para detener."
                )
            except (TypeError, ValueError, OverflowError, OSError):
                pass
            return (
                f"\n\n⏭️ **Modo /loop activo** — timeout {human_interval} desde último mensaje. "
                "`/loop off` para detener."
            )
        if status.get("awaiting_user"):
            return (
                "\n\n⏭️ **Modo /loop activo** — esperando tu respuesta "
                "(turnos agent↔user). `/loop off` para detener."
            )
        return (
            "\n\n⏭️ **Modo /loop activo** — ciclo en curso; tras responder el agente "
            "espera tu mensaje. `/loop off` para detener."
        )
    if not status.get("enabled"):
        return (
            "\n\n⏭️ **Modo /loop:** inactivo. "
            "Activa con `/loop on` (conversación por turnos hasta approve u off)."
        )
    if idle_mode and secs > 0:
        last_act = get_loop_last_activity_epoch(db, chat_id)
        if last_act > 0:
            try:
                next_epoch = last_act + secs
                remaining = max(0, int(next_epoch - ts))
                if next_epoch <= ts:
                    # ponytail: ancla vencida — estimar desde ahora (heartbeat disparará pronto).
                    next_epoch = ts + secs
                    remaining = secs
                clock = datetime.fromtimestamp(next_epoch, tz=tz).strftime("%H:%M")
                remain_h = (
                    format_goals_delta_interval_human(remaining) if remaining > 0 else "< 1 min"
                )
                return (
                    f"\n\n⏭️ **Próximo ciclo /loop --delta:** ~{clock} COT "
                    f"(silencio ~{remain_h} desde último mensaje · intervalo {human_interval})."
                )
            except (TypeError, ValueError, OverflowError, OSError):
                pass
        return (
            f"\n\n⏭️ **Modo /loop --delta:** próximo ciclo tras ~{human_interval} "
            "de silencio desde el último mensaje."
        )
    last_raw = status.get("last_fire_epoch")
    if last_raw:
        try:
            next_epoch = float(last_raw) + secs
            remaining = max(0, int(next_epoch - ts))
            clock = datetime.fromtimestamp(next_epoch, tz=tz).strftime("%H:%M")
            remain_h = format_goals_delta_interval_human(remaining) if remaining > 0 else "< 1 min"
            return (
                f"\n\n⏭️ **Próximo ciclo auto-mejora meditate:** {clock} COT "
                f"(en ~{remain_h} · intervalo {human_interval})."
            )
        except (TypeError, ValueError):
            pass
    try:
        next_epoch = ts + secs
        clock = datetime.fromtimestamp(next_epoch, tz=tz).strftime("%H:%M")
        return (
            f"\n\n⏭️ **Próximo ciclo auto-mejora meditate:** ~{clock} COT "
            f"(en ~{human_interval} · intervalo {human_interval})."
        )
    except (TypeError, ValueError, OverflowError, OSError):
        return f"\n\n⏭️ **Próximo ciclo auto-mejora meditate:** cada ~{human_interval} (Heartbeat)."


def apply_loop_schedule(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str,
    worker_id: str,
    interval_seconds: int,
    vault_user_id: Any = None,
) -> dict[str, Any]:
    """Activa/desactiva programación meditate cognitiva (sin Harness infra)."""
    _ = vault_user_id
    tid = str(tenant_id or "default").strip() or "default"
    wid = (worker_id or "").strip()
    if int(interval_seconds) <= 0:
        clear_loop_schedule(db, chat_id, tenant_id=tid)
        return {"status": "disabled", "enabled": False}
    if not wid or wid.lower() == "manager":
        return {"status": "error", "error": "worker_id missing or manager"}
    secs = max(LOOP_DELTA_MIN_SECONDS, min(int(interval_seconds), LOOP_DELTA_MAX_SECONDS))
    for k, v in (
        (LOOP_DELTA_SECONDS_KEY, str(secs)),
        (LOOP_DELTA_IDLE_KEY, "0"),
        (LOOP_TENANT_KEY, tid),
        (LOOP_WORKER_KEY, wid),
    ):
        ok, err = _persist_loop_chat_state(db, chat_id, k, v, tenant_id=tid)
        if not ok:
            return {"status": "error", "error": err or f"persist failed: {k}"}
    # Ancla ahora: primer tick tras ~intervalo (igual que /crons --delta).
    _persist_loop_chat_state(db, chat_id, LOOP_LAST_FIRE_KEY, str(time.time()), tenant_id=tid)
    human = format_goals_delta_interval_human(secs)
    return {
        "status": "ok",
        "enabled": True,
        "interval_seconds": secs,
        "interval_human": human,
        "worker_id": wid,
        "tenant_id": tid,
        "mode": "clock",
    }


def apply_loop_idle_schedule(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str,
    worker_id: str,
    interval_seconds: int,
) -> dict[str, Any]:
    """Activa /loop --delta: ticks tras silencio desde último mensaje."""
    tid = str(tenant_id or "default").strip() or "default"
    wid = (worker_id or "").strip()
    if int(interval_seconds) <= 0:
        clear_loop_delta_only(db, chat_id, tenant_id=tid)
        return {"status": "disabled", "enabled": False}
    if not wid or wid.lower() == "manager":
        return {"status": "error", "error": "worker_id missing or manager"}
    secs = max(LOOP_DELTA_MIN_SECONDS, min(int(interval_seconds), LOOP_DELTA_MAX_SECONDS))
    for k, v in (
        (LOOP_DELTA_SECONDS_KEY, str(secs)),
        (LOOP_DELTA_IDLE_KEY, "1"),
        (LOOP_ACTIVE_KEY, "0"),
        (LOOP_AWAITING_USER_KEY, "0"),
        (LOOP_LAST_FIRE_KEY, ""),
        (LOOP_TENANT_KEY, tid),
        (LOOP_WORKER_KEY, wid),
    ):
        ok, err = _persist_loop_chat_state(db, chat_id, k, v, tenant_id=tid)
        if not ok:
            return {"status": "error", "error": err or f"persist failed: {k}"}
    # Re-anclar al activar/reconfigurar --delta (evita pie con hora obsoleta de sesión previa).
    touch_loop_last_activity(db, chat_id, tenant_id=tid)
    human = format_goals_delta_interval_human(secs)
    return {
        "status": "ok",
        "enabled": True,
        "interval_seconds": secs,
        "interval_human": human,
        "worker_id": wid,
        "tenant_id": tid,
        "mode": "idle",
    }


def _format_loop_cycle_summary(cycle: dict[str, Any] | None) -> str:
    """Resumen legible (legacy admin / harness)."""
    if not cycle:
        return "sin detalle"
    align_msg = (cycle.get("alignment_message") or "").strip()
    if align_msg:
        return align_msg
    return str(cycle.get("status") or "completed")


def _publish_loop_tick_heartbeat(
    chat_id: Any,
    *,
    tenant_id: str,
    worker_id: str,
    cycle: dict[str, Any] | None,
) -> None:
    publisher = _loop_tick_heartbeat_publisher
    if publisher is None:
        return
    try:
        publisher.publish_loop_tick(
            chat_id,
            tenant_id=tenant_id,
            worker_id=worker_id,
            summary=_format_loop_cycle_summary(cycle),
        )
    except Exception:
        pass


def _resolve_loop_vault_user_id(
    db: Any,
    *,
    vault_user_id: Any = None,
    chat_id: Any = None,
    tenant_id: str = "default",
) -> str:
    """user_id para colas legacy harness (admin)."""
    from duckclaw.vaults import resolve_user_id_for_db_path

    vault = str(Path(getattr(db, "_path", "") or "").expanduser().resolve())
    if not vault:
        return str(vault_user_id or chat_id or tenant_id or "default")
    tid = str(tenant_id or "default").strip() or "default"
    for candidate in (vault_user_id, chat_id, tid):
        uid = resolve_user_id_for_db_path(candidate, vault, tenant_id=tid)
        if uid:
            return uid
    inferred = _infer_user_id_for_audit_queue(vault)
    return inferred if inferred != "default" else str(vault_user_id or chat_id or tid or "default")


def invoke_loop_cycle_for_chat(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str,
    worker_id: str,
    delta_s: int,
    vault_user_id: Any = None,
) -> dict[str, Any]:
    """Legacy Harness infra graph (admin only; no user fly path)."""
    from harness_core.alignment import assess_manifest_alignment
    from harness_core.graphs.loop_graph import invoke_loop_run
    from harness_core.states.loop_state import DomainGoal
    from harness_core.targets import load_homeostasis_manifest, manifest_goals_as_dicts

    from duckclaw.homeostasis.goals_alignment import refresh_goals_list_observations

    vault = str(Path(getattr(db, "_path", "") or "").expanduser().resolve())
    if not vault:
        return {"status": "failed", "error": "vault_db_path missing"}
    user_id = _resolve_loop_vault_user_id(
        db, vault_user_id=vault_user_id, chat_id=chat_id, tenant_id=tenant_id
    )
    manifest = load_homeostasis_manifest(db, tenant_id, chat_id=chat_id)
    refreshed = refresh_goals_list_observations(
        db, chat_id, worker_id, manifest_goals_as_dicts(manifest)
    )
    manifest = manifest.model_copy(
        update={"goals": [DomainGoal.model_validate(g) for g in refreshed]}
    )
    result = invoke_loop_run(
        {
            "tenant_id": tenant_id,
            "worker_id": worker_id,
            "chat_id": str(chat_id),
            "admin_chat_id": str(chat_id),
            "vault_db_path": vault,
            "user_id": user_id,
            "delta_interval_seconds": int(delta_s),
            "targets": manifest.infra.model_dump(),
            "domain_goals": manifest_goals_as_dicts(manifest),
        }
    )
    out = result if isinstance(result, dict) else {"status": "failed", "error": "invalid graph result"}
    try:
        alignment = assess_manifest_alignment(
            manifest,
            out.get("current_metrics") or {},
            db=db,
            chat_id=chat_id,
            worker_id=worker_id,
        )
        out["alignment_message"] = alignment.format_message()
        out["alignment"] = {
            "aligned": alignment.aligned,
            "infra_aligned": alignment.infra_aligned,
            "goals_aligned": alignment.goals_aligned,
        }
    except Exception:
        pass
    return out


def _format_loop_usage(db: Any, chat_id: Any) -> str:
    status = get_loop_schedule_status(db, chat_id)
    lines = [
        "**Uso /loop (auto-mejora cognitiva):**",
        "  `/loop` — ciclo inmediato (one-shot)",
        "  `/loop on` — modo conversación activa (turnos agent↔user hasta approve u off)",
        "  `/loop on --delta 20min` — turnos + timeout si no respondes tras silencio",
        "  `/loop on 4h|20min` — legacy: ticks por reloj (Heartbeat)",
        "  `/loop --delta 4h|off` — auto-ciclo tras silencio desde último mensaje",
        "  `/loop --status` — alineación /goals + próximo ciclo /loop",
        "  `/loop off` — detiene modo activo / programación",
        "Metas en `/goals`.",
    ]
    if status.get("active_mode"):
        wid = status.get("worker_id") or "?"
        waiting = "esperando usuario" if status.get("awaiting_user") else "turno agente"
        if status.get("delta_idle_mode") and int(status.get("interval_seconds") or 0) > 0:
            human = status.get("interval_human") or "?"
            lines.append(
                f"Estado actual: **modo activo + --delta** ({waiting}, timeout ~{human}, worker `{wid}`)."
            )
        else:
            lines.append(f"Estado actual: **modo activo** ({waiting}, worker `{wid}`).")
    elif status.get("enabled"):
        human = status.get("interval_human") or format_goals_delta_interval_human(
            int(status.get("interval_seconds") or 0)
        )
        wid = status.get("worker_id") or "?"
        if status.get("delta_idle_mode"):
            lines.append(
                f"Estado actual: **/loop --delta** tras silencio ~{human} (worker `{wid}`)."
            )
        else:
            lines.append(f"Estado actual: **programado por reloj** cada ~{human} (worker `{wid}`).")
    else:
        lines.append("Estado actual: **inactivo**.")
    return "\n".join(lines)


def _parse_loop_args(raw: str) -> dict[str, Any]:
    """Parsea `/loop on`, `on 4h`, `on --delta 20min`, `--delta 4h`, `--status`, `off`."""
    toks = (raw or "").strip().split()
    idle_dur_frag: str | None = None
    idle_off = False
    status_requested = False
    filtered: list[str] = []
    i = 0
    while i < len(toks):
        low = toks[i].lower()
        if low == "--delta":
            if i + 1 >= len(toks):
                return {"error": "Falta valor tras --delta (ej. 4h, 20min, off)."}
            val = toks[i + 1].strip()
            if val.lower() == "off":
                idle_off = True
                i += 2
                continue
            idle_dur_frag = val
            i += 2
            continue
        if low == "--status":
            status_requested = True
            i += 1
            continue
        filtered.append(toks[i])
        i += 1

    if status_requested:
        if filtered or idle_dur_frag or idle_off:
            return {
                "error": "`/loop --status` no se combina con on/off/--delta. "
                "Usa solo `/loop --status`."
            }
        return {"action": "status"}

    if not filtered:
        if idle_off:
            return {"action": "delta_off"}
        if idle_dur_frag:
            return {"action": "delta", "idle_dur": idle_dur_frag}
        return {"action": "usage"}

    first = filtered[0].lower()
    if first == "off":
        return {"action": "off"}
    if first == "on":
        if len(filtered) == 1:
            if idle_dur_frag:
                return {"action": "on_idle", "idle_dur": idle_dur_frag}
            if idle_off:
                return {"action": "delta_off"}
            return {"action": "on"}
        clock_dur = "".join(filtered[1:])
        if idle_dur_frag:
            return {"action": "on_idle", "idle_dur": idle_dur_frag}
        return {"action": "on_clock", "clock_dur": clock_dur}
    if idle_dur_frag:
        return {"action": "delta", "idle_dur": idle_dur_frag}
    if idle_off:
        return {"action": "delta_off"}
    return {"action": "usage"}


def execute_loop_immediate(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: Any = None,
    vault_user_id: Any = None,
    entry_worker_id: str | None = None,
) -> str:
    """Bare `/loop`, `--self`, `--now`: dispara auto-mejora cognitiva ahora."""
    _ = vault_user_id
    tid = str(tenant_id or "default").strip() or "default"
    worker_id = _resolve_loop_worker_id(
        db, chat_id, tenant_id=tid, entry_worker_id=entry_worker_id
    )
    if not worker_id or worker_id.lower() == "manager":
        return "Asigna un worker al chat (/workers) antes de /loop."
    message = build_loop_self_system_event_message(db, chat_id, tid, scheduled=False)
    vault_path = str(getattr(db, "_path", "") or "").strip() or None
    result = dispatch_loop_self_tick(
        chat_id=chat_id,
        tenant_id=tid,
        worker_id=worker_id,
        message=message,
        vault_db_path=vault_path,
    )
    if not result.get("ok"):
        detail = result.get("error") or result.get("body") or result.get("status_code")
        return f"No se pudo iniciar ciclo meditate: {detail}"
    _publish_loop_tick_heartbeat(
        chat_id,
        tenant_id=tid,
        worker_id=worker_id,
        cycle={"status": "self_tick_dispatched"},
    )
    if is_loop_active_mode(db, chat_id):
        interval_line = "Modo activo por turnos: el agente esperará tu respuesta."
    else:
        interval_human, scheduled = loop_repetition_interval_human(db, chat_id)
        if scheduled:
            interval_line = f"Repetición programada cada ~{interval_human}."
        else:
            interval_line = (
                f"Sin modo activo. Activa con `/loop on` "
                f"(turnos agent↔user; default intervalo legacy ~{interval_human})."
            )
    return (
        f"Ciclo loop iniciado para worker `{worker_id}` (tenant `{tid}`). "
        f"El agente evaluará alineación con /goals. {interval_line}"
    )


def execute_loop_status_with_meta(
    db: Any,
    chat_id: Any,
    args: str = "",
    *,
    tenant_id: str = "default",
    history: list[dict[str, Any]] | None = None,
    vault_db_path: str | None = None,
    worker_id: str | None = None,
    entry_worker_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """``/loop --status``: alineación /goals + pie con próximo ciclo (sin /summarize)."""
    _ = (history, vault_db_path)
    from duckclaw.homeostasis.goals_alignment import (
        assess_goals_alignment,
        format_alignment_report_markdown,
    )

    arg = (args or "").strip().lower()
    if arg in ("help", "-h", "--help"):
        return (
            "Uso: `/loop --status`\n"
            "Muestra alineación con /goals y el pie con el próximo ciclo /loop programado.\n"
            "No compacta el hilo (usa `/summarize` para eso).",
            {},
        )

    tid = str(tenant_id or "default").strip() or "default"
    wid = (
        worker_id
        or _resolve_loop_worker_id(db, chat_id, tenant_id=tid, entry_worker_id=entry_worker_id)
        or ""
    ).strip()
    report = assess_goals_alignment(db, chat_id, worker_id=wid, tenant_id=tid)
    align_block = format_alignment_report_markdown(report)
    footer = format_loop_next_tick_footer(db, chat_id)
    reply = f"✅ Estado /loop\n\n{align_block}{footer}"
    return reply, {}


def execute_loop_status(
    db: Any,
    chat_id: Any,
    args: str = "",
    *,
    tenant_id: str = "default",
    history: list[dict[str, Any]] | None = None,
    vault_db_path: str | None = None,
    worker_id: str | None = None,
    entry_worker_id: str | None = None,
) -> str:
    """Wrapper string-only de ``execute_loop_status_with_meta`` (Telegram/fly)."""
    reply, _meta = execute_loop_status_with_meta(
        db,
        chat_id,
        args,
        tenant_id=tenant_id,
        history=history,
        vault_db_path=vault_db_path,
        worker_id=worker_id,
        entry_worker_id=entry_worker_id,
    )
    return reply


def _execute_loop_enable(
    db: Any,
    chat_id: Any,
    secs: int,
    *,
    tenant_id: str,
    cancel_hint: str = "/loop off",
    entry_worker_id: str | None = None,
) -> str:
    """Legacy: programación por reloj Heartbeat."""
    worker_id = _resolve_loop_worker_id(
        db, chat_id, tenant_id=tenant_id, entry_worker_id=entry_worker_id
    )
    if not worker_id or worker_id.lower() == "manager":
        return "Asigna un worker al chat (/workers) antes de programar /loop."
    # Clock mode: clear turn-based flags first via schedule apply path.
    _persist_loop_chat_state(db, chat_id, LOOP_ACTIVE_KEY, "0", tenant_id=tenant_id)
    _persist_loop_chat_state(db, chat_id, LOOP_AWAITING_USER_KEY, "0", tenant_id=tenant_id)
    applied = apply_loop_schedule(
        db,
        chat_id,
        tenant_id=tenant_id,
        worker_id=worker_id,
        interval_seconds=secs,
    )
    if applied.get("status") == "error":
        return f"No se pudo programar meditate: {applied.get('error')}"
    human = str(applied.get("interval_human") or format_goals_delta_interval_human(secs))
    return (
        f"Auto-mejora meditate cada ~{human} para worker `{worker_id}` (tenant `{tenant_id}`). "
        f"Primer ciclo programado en ~{human}. Metas en /goals. {cancel_hint} para cancelar."
    )


def _execute_loop_active_on(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str,
    entry_worker_id: str | None = None,
    idle_interval_seconds: int = 0,
) -> str:
    """/loop on [--delta dur]: modo conversación por turnos + ciclo inmediato."""
    worker_id = _resolve_loop_worker_id(
        db, chat_id, tenant_id=tenant_id, entry_worker_id=entry_worker_id
    )
    if not worker_id or worker_id.lower() == "manager":
        return "Asigna un worker al chat (/workers) antes de /loop on."
    applied = enable_loop_active_mode(
        db,
        chat_id,
        tenant_id=tenant_id,
        worker_id=worker_id,
        idle_interval_seconds=idle_interval_seconds,
    )
    if applied.get("status") == "error":
        return f"No se pudo activar meditate: {applied.get('error')}"
    touch_loop_last_activity(db, chat_id, tenant_id=tenant_id)
    message = build_loop_self_system_event_message(
        db, chat_id, tenant_id, scheduled=False, active_mode=True
    )
    vault_path = str(getattr(db, "_path", "") or "").strip() or None
    result = dispatch_loop_self_tick(
        chat_id=chat_id,
        tenant_id=tenant_id,
        worker_id=worker_id,
        message=message,
        vault_db_path=vault_path,
    )
    if not result.get("ok"):
        detail = result.get("error") or result.get("body") or result.get("status_code")
        return (
            f"Modo activo guardado, pero falló el primer ciclo: {detail}. "
            "Reintenta `/loop` o `/loop off`."
        )
    _publish_loop_tick_heartbeat(
        chat_id,
        tenant_id=tenant_id,
        worker_id=worker_id,
        cycle={"status": "active_mode_started"},
    )
    timeout_line = ""
    idle_secs = int(idle_interval_seconds or 0)
    if idle_secs > 0:
        human = format_goals_delta_interval_human(idle_secs)
        timeout_line = (
            f" Timeout **--delta** ~{human}: si no respondes, el siguiente ciclo "
            "se dispara tras silencio desde el último mensaje."
        )
    return (
        f"Modo **/loop** activo (turnos agent↔user) para worker `{worker_id}` "
        f"(tenant `{tenant_id}`). Primer ciclo iniciado — el agente reportará en el chat "
        f"y esperará tu respuesta.{timeout_line} Se detiene con `/loop-approve` (homeostasis) o "
        "`/loop off`."
    ) + (
        format_loop_next_tick_footer(db, chat_id)
        if idle_secs > 0
        else ""
    )


def _execute_loop_delta_idle_on(
    db: Any,
    chat_id: Any,
    secs: int,
    *,
    tenant_id: str,
    entry_worker_id: str | None = None,
) -> str:
    """/loop --delta dur: auto-ciclo tras silencio desde último mensaje."""
    worker_id = _resolve_loop_worker_id(
        db, chat_id, tenant_id=tenant_id, entry_worker_id=entry_worker_id
    )
    if not worker_id or worker_id.lower() == "manager":
        return "Asigna un worker al chat (/workers) antes de /loop --delta."
    applied = apply_loop_idle_schedule(
        db,
        chat_id,
        tenant_id=tenant_id,
        worker_id=worker_id,
        interval_seconds=secs,
    )
    if applied.get("status") == "error":
        return f"No se pudo programar /loop --delta: {applied.get('error')}"
    human = str(applied.get("interval_human") or format_goals_delta_interval_human(secs))
    body = (
        f"Modo **/loop --delta** ~{human} para worker `{worker_id}` (tenant `{tenant_id}`). "
        f"Próximo ciclo tras ~{human} de silencio desde el último mensaje (usuario o agente). "
        "Metas en /goals. `/loop --delta off` o `/loop off` para cancelar."
    )
    footer = format_loop_next_tick_footer(db, chat_id)
    if footer and "Próximo ciclo /loop --delta" not in body:
        body += footer
    return body


def execute_loop(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: Any = None,
    vault_user_id: Any = None,
    entry_worker_id: str | None = None,
) -> str:
    """/loop on | on 4h | on --delta | --delta | off."""
    _ = vault_user_id
    tid = str(tenant_id or "default").strip() or "default"
    parsed = _parse_loop_args(args or "")
    if parsed.get("error"):
        return str(parsed["error"])
    action = parsed.get("action") or "usage"

    if action == "usage":
        return _format_loop_usage(db, chat_id)
    if action == "off":
        clear_loop_schedule_all_dbs(db, chat_id, tenant_id=tid)
        return (
            "Modo /loop detenido (/loop off). "
            "Revisión proactiva /crons --delta desactivada en todas las bóvedas del chat."
        )
    if action == "delta_off":
        clear_loop_delta_only(db, chat_id, tenant_id=tid)
        if is_loop_active_mode(db, chat_id):
            return "Timeout /loop --delta desactivado. Modo activo por turnos sigue (`/loop off` para detener)."
        return "Modo /loop --delta desactivado."
    if action == "status":
        return execute_loop_status(
            db,
            chat_id,
            args,
            tenant_id=tid,
            entry_worker_id=entry_worker_id,
        )
    if action == "on":
        return _execute_loop_active_on(
            db, chat_id, tenant_id=tid, entry_worker_id=entry_worker_id
        )
    if action == "on_idle":
        dur_str = str(parsed.get("idle_dur") or "")
        secs, err = parse_loop_delta_arg(dur_str)
        if err:
            return err
        if secs == 0:
            clear_loop_delta_only(db, chat_id, tenant_id=tid)
            return "Timeout /loop --delta desactivado."
        return _execute_loop_active_on(
            db,
            chat_id,
            tenant_id=tid,
            entry_worker_id=entry_worker_id,
            idle_interval_seconds=int(secs),
        )
    if action == "on_clock":
        dur_str = str(parsed.get("clock_dur") or "")
        secs, err = parse_loop_delta_arg(dur_str)
        if err:
            return err
        if secs == 0:
            clear_loop_schedule(db, chat_id, tenant_id=tid)
            return "Modo /loop detenido (/loop off)."
        return _execute_loop_enable(
            db,
            chat_id,
            int(secs),
            tenant_id=tid,
            cancel_hint="/loop off",
            entry_worker_id=entry_worker_id,
        )
    if action == "delta":
        dur_str = str(parsed.get("idle_dur") or "")
        secs, err = parse_loop_delta_arg(dur_str)
        if err:
            return err
        if secs == 0:
            clear_loop_delta_only(db, chat_id, tenant_id=tid)
            return "Modo /loop --delta desactivado."
        return _execute_loop_delta_idle_on(
            db,
            chat_id,
            int(secs),
            tenant_id=tid,
            entry_worker_id=entry_worker_id,
        )
    return _format_loop_usage(db, chat_id)


# --- Legacy /meditate aliases (deprecated; remove release N+2) ---
_LOOP_DELTA_SECONDS_KEY = LOOP_DELTA_SECONDS_KEY
_LOOP_DELTA_IDLE_KEY = LOOP_DELTA_IDLE_KEY
_LOOP_LAST_ACTIVITY_KEY = LOOP_LAST_ACTIVITY_KEY
_LOOP_PENDING_TICK_KEY = LOOP_PENDING_TICK_KEY
_LOOP_LAST_FIRE_KEY = LOOP_LAST_FIRE_KEY
_LOOP_TENANT_KEY = LOOP_TENANT_KEY
_LOOP_WORKER_KEY = LOOP_WORKER_KEY
MEDITATE_DELTA_MIN_SECONDS = LOOP_DELTA_MIN_SECONDS
MEDITATE_DELTA_MAX_SECONDS = LOOP_DELTA_MAX_SECONDS
_MEDITATE_DELTA_SECONDS_KEY = LOOP_DELTA_SECONDS_KEY
_MEDITATE_LAST_FIRE_KEY = LOOP_LAST_FIRE_KEY
_MEDITATE_TENANT_KEY = LOOP_TENANT_KEY
_MEDITATE_WORKER_KEY = LOOP_WORKER_KEY
MEDITATE_SYSTEM_USER_LABEL = LOOP_SYSTEM_USER_LABEL
parse_meditate_delta_arg = parse_loop_delta_arg
chat_id_from_meditate_delta_config_key = chat_id_from_loop_delta_config_key
clear_meditate_schedule = clear_loop_schedule
get_meditate_schedule_status = get_loop_schedule_status
apply_meditate_schedule = apply_loop_schedule
_format_meditate_cycle_summary = _format_loop_cycle_summary
_publish_meditate_tick_heartbeat = _publish_loop_tick_heartbeat
_resolve_meditate_vault_user_id = _resolve_loop_vault_user_id
invoke_meditate_cycle_for_chat = invoke_loop_cycle_for_chat
execute_meditate = execute_loop
execute_meditate_immediate = execute_loop_immediate
is_meditate_active_mode = is_loop_active_mode
is_meditate_awaiting_user = is_loop_awaiting_user
set_meditate_awaiting_user = set_loop_awaiting_user
format_meditate_next_tick_footer = format_loop_next_tick_footer
build_meditate_active_user_continuation = build_loop_active_user_continuation
build_meditate_self_system_event_message = build_loop_self_system_event_message
dispatch_meditate_self_tick = dispatch_loop_self_tick
post_meditate_self_tick_sync = post_loop_self_tick_sync
