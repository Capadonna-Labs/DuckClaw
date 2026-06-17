"""DB-first infra meditate scheduling commands for /meditate --delta."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional, Protocol

from duckclaw.commands.chat_state import (
    _PREFIX,
    _skip_runtime_ddl,
    get_chat_state,
    set_chat_state,
    set_chat_state_via_typed_command,
)
from duckclaw.commands.crons import (
    _GOALS_DELTA_SECONDS_KEY,
    format_goals_delta_interval_human,
    parse_goals_delta_arg,
)
from duckclaw.commands.history import _infer_user_id_for_audit_queue

_MEDITATE_DELTA_SECONDS_KEY = "meditate_delta_seconds"
_MEDITATE_LAST_FIRE_KEY = "meditate_last_fire_epoch"
_MEDITATE_TENANT_KEY = "meditate_tenant_id"
_MEDITATE_WORKER_KEY = "meditate_worker_id"
MEDITATE_DELTA_MIN_SECONDS = 60
MEDITATE_DELTA_MAX_SECONDS = 7 * 24 * 3600


class MeditateTickHeartbeatPublisher(Protocol):
    def publish_meditate_tick(
        self,
        chat_id: Any,
        *,
        tenant_id: str,
        worker_id: str,
        summary: str,
    ) -> None: ...


_meditate_tick_heartbeat_publisher: MeditateTickHeartbeatPublisher | None = None


def configure_meditate_tick_heartbeat_publisher(
    publisher: MeditateTickHeartbeatPublisher | None,
) -> None:
    """Inject admin UI heartbeat publisher from the graph facade."""
    global _meditate_tick_heartbeat_publisher
    _meditate_tick_heartbeat_publisher = publisher


def parse_meditate_delta_arg(fragment: str) -> tuple[Optional[int], Optional[str]]:
    """Alias de parse_goals_delta_arg con mismos límites de intervalo."""
    return parse_goals_delta_arg(fragment)


def chat_id_from_meditate_delta_config_key(key: str) -> Optional[str]:
    """Extrae chat_id desde fila agent_config con sufijo _meditate_delta_seconds."""
    suf = f"_{_MEDITATE_DELTA_SECONDS_KEY}"
    if not key.startswith(_PREFIX) or not key.endswith(suf):
        return None
    return key[len(_PREFIX) : -len(suf)] or None


def _persist_meditate_chat_state(
    db: Any,
    chat_id: Any,
    key_suffix: str,
    value: str,
    *,
    tenant_id: str = "default",
) -> tuple[bool, str]:
    tid = str(tenant_id or "default").strip() or "default"
    if _skip_runtime_ddl(db):
        return set_chat_state_via_typed_command(
            db,
            chat_id,
            key_suffix,
            value,
            tenant_id=tid,
        )
    set_chat_state(db, chat_id, key_suffix, value)
    return True, ""


def clear_meditate_schedule(db: Any, chat_id: Any, *, tenant_id: str = "default") -> None:
    """Desactiva el programador meditate para el chat."""
    tid = str(tenant_id or "default").strip() or "default"
    for k, v in (
        (_MEDITATE_DELTA_SECONDS_KEY, "0"),
        (_MEDITATE_LAST_FIRE_KEY, ""),
        (_MEDITATE_TENANT_KEY, ""),
        (_MEDITATE_WORKER_KEY, ""),
    ):
        _persist_meditate_chat_state(db, chat_id, k, v, tenant_id=tid)


def get_meditate_schedule_status(db: Any, chat_id: Any) -> dict[str, Any]:
    """Estado actual del termostato infra meditate para este chat."""
    try:
        secs = int((get_chat_state(db, chat_id, _MEDITATE_DELTA_SECONDS_KEY) or "0").strip() or "0")
    except ValueError:
        secs = 0
    return {
        "enabled": secs > 0,
        "interval_seconds": secs,
        "interval_human": format_goals_delta_interval_human(secs) if secs > 0 else None,
        "tenant_id": (get_chat_state(db, chat_id, _MEDITATE_TENANT_KEY) or "").strip() or None,
        "worker_id": (get_chat_state(db, chat_id, _MEDITATE_WORKER_KEY) or "").strip() or None,
        "last_fire_epoch": (get_chat_state(db, chat_id, _MEDITATE_LAST_FIRE_KEY) or "").strip() or None,
    }


def apply_meditate_schedule(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str,
    worker_id: str,
    interval_seconds: int,
    run_first_cycle: bool = True,
    vault_user_id: Any = None,
) -> dict[str, Any]:
    """Activa/desactiva meditate y opcionalmente ejecuta el primer ciclo."""
    tid = str(tenant_id or "default").strip() or "default"
    wid = (worker_id or "").strip()
    if int(interval_seconds) <= 0:
        clear_meditate_schedule(db, chat_id, tenant_id=tid)
        return {"status": "disabled", "enabled": False}
    if not wid or wid.lower() == "manager":
        return {"status": "error", "error": "worker_id missing or manager"}
    secs = max(MEDITATE_DELTA_MIN_SECONDS, min(int(interval_seconds), MEDITATE_DELTA_MAX_SECONDS))
    for k, v in (
        (_MEDITATE_DELTA_SECONDS_KEY, str(secs)),
        (_MEDITATE_TENANT_KEY, tid),
        (_MEDITATE_WORKER_KEY, wid),
    ):
        ok, err = _persist_meditate_chat_state(db, chat_id, k, v, tenant_id=tid)
        if not ok:
            return {"status": "error", "error": err or f"persist failed: {k}"}
    human = format_goals_delta_interval_human(secs)
    out: dict[str, Any] = {
        "status": "ok",
        "enabled": True,
        "interval_seconds": secs,
        "interval_human": human,
        "worker_id": wid,
        "tenant_id": tid,
    }
    if not run_first_cycle:
        _persist_meditate_chat_state(db, chat_id, _MEDITATE_LAST_FIRE_KEY, "0", tenant_id=tid)
        return out
    try:
        result = invoke_meditate_cycle_for_chat(
            db,
            chat_id,
            tenant_id=tid,
            worker_id=wid,
            delta_s=secs,
            vault_user_id=vault_user_id,
        )
        out["first_cycle"] = result
        if str(result.get("status") or "") == "failed":
            _persist_meditate_chat_state(db, chat_id, _MEDITATE_LAST_FIRE_KEY, "0", tenant_id=tid)
            out["first_cycle_error"] = result.get("error")
        else:
            _persist_meditate_chat_state(
                db, chat_id, _MEDITATE_LAST_FIRE_KEY, str(time.time()), tenant_id=tid
            )
            out["first_cycle_executed"] = True
            _publish_meditate_tick_heartbeat(
                chat_id, tenant_id=tid, worker_id=wid, cycle=result if isinstance(result, dict) else None
            )
    except Exception as exc:
        _persist_meditate_chat_state(db, chat_id, _MEDITATE_LAST_FIRE_KEY, "0", tenant_id=tid)
        out["first_cycle_error"] = str(exc)
    return out


def _format_meditate_cycle_summary(cycle: dict[str, Any] | None) -> str:
    """Resumen legible del último ciclo meditate (para fly/scheduler/admin UI)."""
    if not cycle:
        return "sin detalle"
    align_msg = (cycle.get("alignment_message") or "").strip()
    if align_msg:
        return align_msg
    status = str(cycle.get("status") or "unknown")
    dist = cycle.get("distance_vector") or {}
    actions = cycle.get("dispatched_actions") or []
    action_bits: list[str] = []
    for raw in actions:
        if not isinstance(raw, dict):
            continue
        at = str(raw.get("action_type") or "?")
        ex = "ok" if raw.get("executed") else "pendiente"
        action_bits.append(f"{at}({ex})")
    metric_bits: list[str] = []
    for key in ("stale_tasks_count", "error_rate_pct", "memory_fragmentation_index", "db_lock_events"):
        try:
            val = float(dist.get(key) or 0)
        except (TypeError, ValueError):
            val = 0.0
        if val:
            metric_bits.append(f"{key}={val:g}")
    parts = [f"estado={status}"]
    if action_bits:
        parts.append("acciones=" + ", ".join(action_bits))
    if metric_bits:
        parts.append("métricas=" + ", ".join(metric_bits))
    run_id = str(cycle.get("run_id") or "").strip()
    if run_id:
        parts.append(f"run={run_id[:8]}")
    return "; ".join(parts)


def _publish_meditate_tick_heartbeat(
    chat_id: Any,
    *,
    tenant_id: str,
    worker_id: str,
    cycle: dict[str, Any] | None,
) -> None:
    """Notifica en admin UI que un ciclo meditate terminó (infra, sin turno LLM)."""
    publisher = _meditate_tick_heartbeat_publisher
    if publisher is None:
        return
    try:
        publisher.publish_meditate_tick(
            chat_id,
            tenant_id=tenant_id,
            worker_id=worker_id,
            summary=_format_meditate_cycle_summary(cycle),
        )
    except Exception:
        pass


def _resolve_meditate_vault_user_id(
    db: Any,
    *,
    vault_user_id: Any = None,
    chat_id: Any = None,
    tenant_id: str = "default",
) -> str:
    """user_id para cola MEDITATE_STATE_DELTA (debe pasar validate_user_db_path)."""
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


def invoke_meditate_cycle_for_chat(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str,
    worker_id: str,
    delta_s: int,
    vault_user_id: Any = None,
) -> dict[str, Any]:
    """Dispara un ciclo meditate contra la bóveda del handle fly."""
    from harness_core.alignment import assess_manifest_alignment
    from harness_core.graphs.meditate_graph import invoke_meditate_run
    from harness_core.states.meditate_state import DomainGoal
    from harness_core.targets import load_homeostasis_manifest, manifest_goals_as_dicts

    from duckclaw.homeostasis.goals_alignment import refresh_goals_list_observations

    vault = str(Path(getattr(db, "_path", "") or "").expanduser().resolve())
    if not vault:
        return {"status": "failed", "error": "vault_db_path missing"}
    user_id = _resolve_meditate_vault_user_id(
        db, vault_user_id=vault_user_id, chat_id=chat_id, tenant_id=tenant_id
    )
    manifest = load_homeostasis_manifest(db, tenant_id, chat_id=chat_id)
    refreshed = refresh_goals_list_observations(
        db, chat_id, worker_id, manifest_goals_as_dicts(manifest)
    )
    manifest = manifest.model_copy(
        update={"goals": [DomainGoal.model_validate(g) for g in refreshed]}
    )
    result = invoke_meditate_run(
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
        for action in out.get("dispatched_actions") or []:
            if isinstance(action, dict) and action.get("action_type") == "noop":
                action["alignment_message"] = out["alignment_message"]
    except Exception:
        pass
    return out


def execute_meditate(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: Any = None,
    vault_user_id: Any = None,
) -> str:
    """/meditate --delta 4h | /meditate --delta off — termostato infra Harness Core."""
    tid = str(tenant_id or "default").strip() or "default"
    raw = (args or "").strip()
    toks = raw.split()
    if not toks or toks[0] != "--delta":
        return (
            "Uso: /meditate --delta 4h · /meditate --delta off\n"
            "Termostato de infraestructura (telemetría DuckDB → acciones correctivas). "
            "Independiente de /crons --delta."
        )
    if len(toks) < 2:
        return "Falta valor tras --delta (ej. 4h, 20min, off)."
    dur_str = "".join(toks[1:])
    secs, err = parse_meditate_delta_arg(dur_str)
    if err:
        return err
    if secs == 0:
        clear_meditate_schedule(db, chat_id, tenant_id=tid)
        return "Meditate desactivado (/meditate --delta off)."
    worker_id = (get_chat_state(db, chat_id, "worker_id") or "").strip()
    if not worker_id or worker_id.lower() == "manager":
        return "Asigna un worker al chat (/workers) antes de programar /meditate --delta."
    applied = apply_meditate_schedule(
        db,
        chat_id,
        tenant_id=tid,
        worker_id=worker_id,
        interval_seconds=secs,
        run_first_cycle=True,
        vault_user_id=vault_user_id,
    )
    if applied.get("status") == "error":
        return f"No se pudo programar meditate: {applied.get('error')}"
    human = str(applied.get("interval_human") or format_goals_delta_interval_human(secs))
    first_cycle_note = ""
    if applied.get("first_cycle_executed"):
        fc = applied.get("first_cycle") if isinstance(applied.get("first_cycle"), dict) else {}
        first_cycle_note = f" Primer ciclo: {_format_meditate_cycle_summary(fc)};"
    elif applied.get("first_cycle_error"):
        first_cycle_note = (
            f" Primer ciclo falló: {applied.get('first_cycle_error')}; "
            "el programador reintentará en el próximo intervalo."
        )
    try:
        crons_secs = int((get_chat_state(db, chat_id, _GOALS_DELTA_SECONDS_KEY) or "0").strip() or "0")
    except ValueError:
        crons_secs = 0
    crons_hint = ""
    if crons_secs <= 0:
        crons_hint = (
            " Para que el **agente** revise goals y hable de forma proactiva (SYSTEM_EVENT), "
            f"activa también `/crons --delta {human}`."
        )
    return (
        f"Meditate infra cada ~{human} para worker `{worker_id}` (tenant `{tid}`)."
        f"{first_cycle_note} próximo ciclo infra en ~{human}."
        f"{crons_hint} "
        "Meditate no despierta al LLM; solo telemetría y correcciones en DuckDB. "
        "/meditate --delta off para cancelar."
    )
