"""
On-the-Fly CLI: comandos de Telegram que mutan estado del grafo sin reiniciar.

Spec: specs/interfaz_de_comandos_dinamicos_On-the-Fly_CLI.md
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional, Tuple
from duckclaw.commands.chat_state import (
    _AGENT_CONFIG_TABLE as _AGENT_CONFIG_TABLE,
    _PREFIX as _PREFIX,
    _chat_key as _chat_key,
    _ensure_agent_config as _ensure_agent_config,
    _get_global_config as _get_global_config,
    _set_global_config as _set_global_config,
    _skip_runtime_ddl as _skip_runtime_ddl,
    get_chat_state as get_chat_state,
    set_chat_state as set_chat_state,
)
from duckclaw.commands.crons import (
    CRON_SCHEDULE_ID_DELTA as CRON_SCHEDULE_ID_DELTA,
    CRON_SCHEDULE_ID_WALL as CRON_SCHEDULE_ID_WALL,
    GOALS_DELTA_MAX_SECONDS as GOALS_DELTA_MAX_SECONDS,
    GOALS_DELTA_MIN_SECONDS as GOALS_DELTA_MIN_SECONDS,
    _GOALS_CRON_WALL_KEY as _GOALS_CRON_WALL_KEY,
    _GOALS_DELTA_ANCHOR_LEGACY_KEY as _GOALS_DELTA_ANCHOR_LEGACY_KEY,
    _GOALS_DELTA_META_KEY as _GOALS_DELTA_META_KEY,
    _GOALS_DELTA_SECONDS_KEY as _GOALS_DELTA_SECONDS_KEY,
    _GOALS_PROACTIVE_ANCHOR_KEY as _GOALS_PROACTIVE_ANCHOR_KEY,
    _GOALS_PROACTIVE_LAST_FIRE_KEY as _GOALS_PROACTIVE_LAST_FIRE_KEY,
    _GOALS_PROACTIVE_NOTIFY_KEY as _GOALS_PROACTIVE_NOTIFY_KEY,
    _GOALS_PROACTIVE_TENANT_KEY as _GOALS_PROACTIVE_TENANT_KEY,
    _apply_interval_only_clear as _apply_interval_only_clear,
    _crons_debug_log as _crons_debug_log,
    _crons_goals_delta_listing_section as _crons_goals_delta_listing_section,
    _crons_goals_delta_meta_dict as _crons_goals_delta_meta_dict,
    _extract_crons_delta_options as _extract_crons_delta_options,
    _goals_cron_wall_listing_note as _goals_cron_wall_listing_note,
    _goals_proactive_interval_countdown_parts as _goals_proactive_interval_countdown_parts,
    _normalize_cron_rm_id as _normalize_cron_rm_id,
    _short_session_uid_for_crons as _short_session_uid_for_crons,
    build_goals_proactive_system_event_message as build_goals_proactive_system_event_message,
    chat_id_from_goals_cron_wall_key as chat_id_from_goals_cron_wall_key,
    chat_id_from_goals_delta_config_key as chat_id_from_goals_delta_config_key,
    clear_goals_cron_wall_storage as clear_goals_cron_wall_storage,
    clear_goals_proactive_schedule as clear_goals_proactive_schedule,
    clear_interval_schedule_only as clear_interval_schedule_only,
    execute_crons_schedule as execute_crons_schedule,
    execute_goals as execute_goals,
    format_goals_countdown_human as format_goals_countdown_human,
    format_goals_delta_interval_human as format_goals_delta_interval_human,
    format_platform_cron_summary as format_platform_cron_summary,
    parse_goals_delta_arg as parse_goals_delta_arg,
)
from duckclaw.commands.goals import (
    _format_homeostasis_manifest_listing as _format_homeostasis_manifest_listing,
    _get_goals_registry_fallback_first as _get_goals_registry_fallback_first,
    _get_goals_registry_for_chat as _get_goals_registry_for_chat,
    _goal_title as _goal_title,
    _natural_language_goal_to_params as _natural_language_goal_to_params,
    _normalize_belief_key as _normalize_belief_key,
    _persist_homeostasis_manifest_db as _persist_homeostasis_manifest_db,
    configure_goals_llm_triplet_resolver as _configure_goals_llm_triplet_resolver,
    configure_goals_vault_user_id_resolver as _configure_goals_vault_user_id_resolver,
    execute_homeostasis_goals as execute_homeostasis_goals,
    get_manager_goals as get_manager_goals,
    set_manager_goals as set_manager_goals,
)
from duckclaw.commands.team_templates import (
    _canonicalize_team_template_ids as _canonicalize_team_template_ids,
    _resolve_template_id as _resolve_template_id,
    _sync_tenant_team_if_admin as _sync_tenant_team_if_admin,
    _tenant_team_config_key as _tenant_team_config_key,
    configure_team_template_admin_checker as _configure_team_template_admin_checker,
    execute_team as execute_team,
    get_effective_team_templates as get_effective_team_templates,
    get_team_templates as get_team_templates,
    get_tenant_team_templates as get_tenant_team_templates,
    set_team_templates as set_team_templates,
    set_tenant_team_templates as set_tenant_team_templates,
)
from duckclaw.commands.team_access import (
    _AUTHORIZED_USERS_DDL as _AUTHORIZED_USERS_DDL,
    _AUTHORIZED_USERS_TABLE as _AUTHORIZED_USERS_TABLE,
    _audit_team_whitelist_rw as _audit_team_whitelist_rw,
    _authorized_users_rw_connection as _authorized_users_rw_connection,
    _dedupe_authorized_users_by_user_id as _dedupe_authorized_users_by_user_id,
    _delete_authorized_user as _delete_authorized_user,
    _ensure_authorized_users_table as _ensure_authorized_users_table,
    _get_authorized_role as _get_authorized_role,
    _invalidate_whitelist_redis_cache as _invalidate_whitelist_redis_cache,
    _is_gateway_owner_user as _is_gateway_owner_user,
    _is_team_admin as _is_team_admin,
    _list_authorized_users as _list_authorized_users,
    _paths_same_duckdb_file as _paths_same_duckdb_file,
    _player_label as _player_label,
    _player_label_log as _player_label_log,
    _resolve_team_add_uid_and_username as _resolve_team_add_uid_and_username,
    _sql_escape_literal as _sql_escape_literal,
    _team_username_by_user_id as _team_username_by_user_id,
    _team_whitelist_audit_enabled as _team_whitelist_audit_enabled,
    _team_whitelist_db as _team_whitelist_db,
    _try_duckdb_checkpoint_rw as _try_duckdb_checkpoint_rw,
    _upsert_authorized_user as _upsert_authorized_user,
    configure_team_access_acl_db_provider as _configure_team_access_acl_db_provider,
    execute_team_whitelist as execute_team_whitelist,
)
from duckclaw.commands.vaults import (
    _dedicated_gateway_db_path_for_vault as _dedicated_gateway_db_path_for_vault,
    _dedicated_gateway_vault_label as _dedicated_gateway_vault_label,
    _effective_vault_tenant_label as _effective_vault_tenant_label,
    _fly_vault_label_for_tenant as _fly_vault_label_for_tenant,
    _format_vault_size_mb as _format_vault_size_mb,
    _session_duckdb_path_for_fly as _session_duckdb_path_for_fly,
    _template_bound_vault_path as _template_bound_vault_path,
    execute_vault as execute_vault,
)

from duckclaw.guardrails.loader import format_guardrail, load_guardrail, load_guardrail_pipe_table
from duckclaw.utils.logger import format_chat_log_identity, get_obs_logger, log_fly, structured_log_context
from duckclaw.utils.telegram_markdown_v2 import TELEGRAM_MARKDOWN_V2_SPECIAL

def _team_access_acl_db_provider() -> Any:
    from duckclaw.graphs.graph_server import get_db

    return get_db()


_configure_team_access_acl_db_provider(_team_access_acl_db_provider)


# Termostato infra meditate (/meditate --delta); independiente de /crons --delta
_MEDITATE_DELTA_SECONDS_KEY = "meditate_delta_seconds"
_MEDITATE_LAST_FIRE_KEY = "meditate_last_fire_epoch"
_MEDITATE_TENANT_KEY = "meditate_tenant_id"
_MEDITATE_WORKER_KEY = "meditate_worker_id"
MEDITATE_DELTA_MIN_SECONDS = 60
MEDITATE_DELTA_MAX_SECONDS = 7 * 24 * 3600

# Cola FIFO de PNG base64 por chat: api-gateway hace pop_all y sendPhoto en orden.
_FLY_OUTBOUND_CHART_B64: dict[str, list[str]] = {}


def _debug_log_model_config(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, Any],
    run_id: str = "gemini_cfg_debug_v1",
) -> None:
    """Reserved for optional NDJSON debug (no-op)."""
    del hypothesis_id, location, message, data, run_id


_FLY_OUTBOUND_CHART_NAMES: dict[str, list[str]] = {}


def register_fly_outbound_chart_b64(
    session_id: Any, b64: str, *, chart_name: str | None = None
) -> None:
    s = (b64 or "").strip()
    if not s:
        return
    k = str(session_id).strip()
    _FLY_OUTBOUND_CHART_B64.setdefault(k, []).append(s)
    if chart_name and str(chart_name).strip():
        _FLY_OUTBOUND_CHART_NAMES.setdefault(k, []).append(str(chart_name).strip())


def pop_all_fly_outbound_charts(session_id: Any) -> tuple[list[str], list[str]]:
    """Devuelve y vacía figuras encoladas (b64, nombres legibles) en orden FIFO."""
    k = str(session_id).strip()
    charts_b64 = _FLY_OUTBOUND_CHART_B64.pop(k, [])
    chart_names = _FLY_OUTBOUND_CHART_NAMES.pop(k, [])
    while len(chart_names) < len(charts_b64):
        chart_names.append(f"chart-{len(chart_names) + 1}.png")
    return charts_b64, chart_names


def pop_all_fly_outbound_charts_b64(session_id: Any) -> list[str]:
    """Devuelve y vacía todas las figuras encoladas para este chat (orden FIFO)."""
    charts_b64, _ = pop_all_fly_outbound_charts(session_id)
    return charts_b64


def pop_fly_outbound_chart_b64(session_id: Any) -> str | None:
    """Compat: saca solo el primer PNG de la cola; preferir pop_all en el gateway."""
    k = str(session_id).strip()
    q = _FLY_OUTBOUND_CHART_B64.get(k)
    if not q:
        return None
    first = q.pop(0)
    if not q:
        del _FLY_OUTBOUND_CHART_B64[k]
    return first


def parse_meditate_delta_arg(fragment: str) -> tuple[Optional[int], Optional[str]]:
    """Alias de parse_goals_delta_arg con mismos límites de intervalo."""
    return parse_goals_delta_arg(fragment)


def chat_id_from_meditate_delta_config_key(key: str) -> Optional[str]:
    """Extrae chat_id desde fila agent_config con sufijo _meditate_delta_seconds."""
    suf = f"_{_MEDITATE_DELTA_SECONDS_KEY}"
    if not key.startswith(_PREFIX) or not key.endswith(suf):
        return None
    return key[len(_PREFIX) : -len(suf)] or None


def set_chat_state_via_vault(
    db: Any,
    chat_id: Any,
    key_suffix: str,
    value: str,
    *,
    tenant_id: str = "default",
) -> tuple[bool, str]:
    """Persist chat-scoped command state through DB-writer when the current handle is read-only."""
    if not _skip_runtime_ddl(db):
        set_chat_state(db, chat_id, key_suffix, value)
        return True, ""

    raw_path = str(getattr(db, "_path", "") or "").strip()
    if not raw_path or raw_path == ":memory:":
        return False, "Ruta de bóveda no resuelta"

    try:
        from duckclaw.db_write_queue import enqueue_duckdb_write_sync, poll_task_status_sync
    except Exception as exc:
        return False, f"cola DuckDB no disponible: {exc}"

    released_ro = False
    try:
        release = getattr(db, "release_file_handle_for_external_writer", None)
        resume = getattr(db, "resume_readonly_file_handle", None)
        suspend = getattr(db, "suspend_readonly_file_handle", None)
        if callable(release):
            release()
            released_ro = bool(callable(resume))
        elif callable(suspend) and callable(resume):
            suspend()
            released_ro = True

        query = (
            "INSERT INTO agent_config (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP"
        )
        task_id = enqueue_duckdb_write_sync(
            db_path=str(Path(raw_path).expanduser().resolve()),
            query=query,
            params=[_chat_key(chat_id, key_suffix)[:240], str(value)[:16384]],
            user_id=str(chat_id),
            tenant_id=str(tenant_id or "default").strip() or "default",
        )
        status = poll_task_status_sync(task_id, timeout_sec=30.0)
        if status is None:
            return False, "timeout esperando db-writer"
        if status.status != "success":
            return False, (status.detail or "db-writer failed")[:500]
        return True, ""
    finally:
        if released_ro:
            try:
                if callable(resume):
                    resume()
            except Exception:
                pass


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
        return set_chat_state_via_vault(db, chat_id, key_suffix, value, tenant_id=tid)
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
    try:
        from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session, publish_admin_chat_heartbeat

        cid = str(chat_id or "").strip()
        if not cid or not is_admin_ui_chat_session(cid):
            return
        publish_admin_chat_heartbeat(
            cid,
            f"[meditate] {_format_meditate_cycle_summary(cycle)}",
            kind="meditate_tick",
            worker_id=worker_id,
            artifact_tenant_id=tenant_id,
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
    from pathlib import Path

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


_configure_goals_vault_user_id_resolver(_resolve_meditate_vault_user_id)


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
    from pathlib import Path

    from harness_core.alignment import assess_manifest_alignment
    from harness_core.graphs.meditate_graph import invoke_meditate_run
    from harness_core.states.meditate_state import DomainGoal
    from harness_core.targets import load_homeostasis_manifest, manifest_goals_as_dicts
    from duckclaw.forge.homeostasis.goals_alignment import refresh_goals_list_observations

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


def unescape_telegram_markdown_v2_layers(text: str, max_layers: int = 4) -> str:
    """
    Quita hasta ``max_layers`` capas de escape estilo MarkdownV2 (mismo juego de
    caracteres que ``escape_telegram_markdown_v2``). Sirve para:

    - Historial que reinyecta la respuesta HTTP ya escapada (cliente / gateway).
    - Salidas del modelo que copian ``\\.``, ``\\!``, ``\\*`` del contexto.

    Sin esto, el escape MDV2 vuelve a escapar las barras y el texto crece
    (p. ej. ``\\!`` → ``\\\\!`` → ``\\\\\\!``).
    """
    if not text:
        return ""
    esc = frozenset(TELEGRAM_MARKDOWN_V2_SPECIAL)
    t = str(text)
    for _ in range(max(1, int(max_layers))):
        out: list[str] = []
        i = 0
        while i < len(t):
            if t[i] == "\\" and i + 1 < len(t) and t[i + 1] in esc:
                out.append(t[i + 1])
                i += 2
            else:
                out.append(t[i])
                i += 1
        t_new = "".join(out)
        if t_new == t:
            return t_new
        t = t_new
    return t

def parse_command(text: str) -> Tuple[str, str]:
    """Parse /command or /command args. Returns (name, args)."""
    if not text or not text.strip().startswith("/"):
        return "", ""
    parts = text.strip().split(maxsplit=1)
    name = (parts[0] or "").lstrip("/").lower()
    if "@" in name:
        name = name.split("@", 1)[0]
    args = (parts[1] if len(parts) > 1 else "").strip()
    return name, args


def execute_roles(db: Any, chat_id: Any) -> str:
    """/roles: lista todos los trabajadores virtuales (templates) disponibles. El manager solo delegará a los que estén en /workers."""
    from duckclaw.workers.factory import list_workers
    all_templates = list_workers()
    if not all_templates:
        return "No hay templates en forge/templates. Añade al menos uno."
    lines = "\n".join(f"- {w}" for w in all_templates)
    return format_guardrail("fly_commands", "roles_list_intro", lines=lines)


# Worker por defecto: el manager orquesta y delega a los trabajadores en forge/templates
_DEFAULT_WORKER = "manager"


def execute_role_switch(db: Any, chat_id: Any, worker_id: str) -> str:
    """/role <worker_id>: cambia el rol. Por defecto 'manager' delega a los templates. Sin args: muestra rol actual y disponibles."""
    from duckclaw.workers.factory import list_workers
    available = list_workers()
    wid_raw = (worker_id or "").strip()
    if not wid_raw:
        current = get_chat_state(db, chat_id, "worker_id") or _DEFAULT_WORKER
        if current == "manager":
            current_display = "Manager (delega a trabajadores en templates)"
        else:
            try:
                from duckclaw.workers.manifest import load_manifest
                spec = load_manifest(current)
                current_display = f"{spec.name} ({current})"
            except Exception:
                current_display = current
        avail_str = "\n".join(f"- {w}" for w in available) if available else "ninguna"
        return (
            f"🦆 Rol: {current_display}\n\n"
            f"Disponibles: manager (por defecto)\n{avail_str}\n/role <id>"
        )
    if wid_raw.lower() == "manager":
        set_chat_state(db, chat_id, "worker_id", "manager")
        return "✅ Manager. Delega a los trabajadores en templates."
    canonical = _resolve_template_id(available, wid_raw)
    if not canonical:
        avail_str = "\n".join(f"- {w}" for w in available) if available else "ninguna"
        return f"Rol '{wid_raw}' no existe.\nDisponibles:\n{avail_str}"
    try:
        from duckclaw.workers.manifest import load_manifest
        spec = load_manifest(canonical)
        set_chat_state(db, chat_id, "worker_id", canonical)
        skills = ", ".join(spec.skills_list or []) or "read_sql, admin_sql"
        return f"✅ {spec.name} ({canonical}). Herramientas: {skills}"
    except Exception as e:
        return f"Error al cargar rol: {e}."


def execute_skills_list(db: Any, chat_id: Any, args: str) -> str:
    """/skills <worker_id>: lista herramientas del template. worker_id debe ser uno de /roles."""
    from duckclaw.workers.factory import list_workers
    available = list_workers()
    wid_raw = (args or "").strip()
    if not wid_raw:
        return "Uso: /skills <worker_id>. Ver templates: /roles"
    if wid_raw.startswith("--"):
        return "Indica un worker_id (ej. research_worker). Ver templates: /roles"
    canonical = _resolve_template_id(available, wid_raw)
    if not canonical:
        return f"Template '{wid_raw}' no encontrado. Disponibles (usa /roles): {', '.join(available)}"
    try:
        from duckclaw.workers.manifest import load_manifest
        spec = load_manifest(canonical)
        skill_lines = [f"- {s}" for s in (spec.skills_list or [])]
        skill_lines.append("- read_sql (solo lectura)")
        skill_lines.append("- admin_sql (lectura + escrituras)")
        return f"🔧 {spec.name} ({canonical})\n" + "\n".join(skill_lines)
    except Exception as e:
        return f"Error: {e}."


def execute_forget(db: Any, chat_id: Any) -> str:
    """/forget: borra historial de la conversación y reinicia estado."""
    try:
        cid = int(chat_id)
        # Telegram: chat_id is numeric, use telegram_conversation
        db.execute(f"DELETE FROM telegram_conversation WHERE chat_id = {cid}")
    except (TypeError, ValueError):
        # API gateway: session_id is string (e.g. "default"), use api_conversation
        sid = str(chat_id).replace("'", "''")[:256]
        try:
            db.execute(f"DELETE FROM api_conversation WHERE session_id = '{sid}'")
        except Exception:
            pass  # Table may not exist if only Telegram used
    try:
        set_chat_state(db, chat_id, "last_audit", "")
    except Exception:
        pass
    if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true":
        try:
            import langsmith
            # Log evento Habeas Data (opcional: run_id no disponible aquí)
            pass
        except Exception:
            pass
    return "✅ Historial borrado."



def execute_context_toggle(db: Any, chat_id: Any, on_off: str) -> str:
    """/context on|off: activa o desactiva inyección de memoria a largo plazo."""
    v = (on_off or "").strip().lower()
    if v in ("on", "1", "true", "sí", "si"):
        set_chat_state(db, chat_id, "use_rag", "true")
        return "✅ Contexto largo activado (más mensajes en historial)."
    if v in ("off", "0", "false"):
        set_chat_state(db, chat_id, "use_rag", "false")
        return "✅ Contexto largo desactivado (solo historial reciente)."
    current = get_chat_state(db, chat_id, "use_rag")
    return (
        "Uso: `/context on` | `/context off` | `/context --add` [texto o pie de foto en imagen/álbum] | "
        "`/context --summary` (`--summarize`)\n"
        f"Estado actual (historial largo): {'on' if current != 'false' else 'off'}."
    )


def execute_comfyui_provider(db: Any, chat_id: Any, args: str) -> str:
    """/comfyui --provider local|fal: motor de generacion visual por chat."""
    from duckclaw.forge.skills.visual_provider import (
        default_visual_provider,
        provider_status_message,
        resolve_visual_provider,
    )

    raw = (args or "").strip()
    if raw.startswith("--provider"):
        val = raw[len("--provider"):].strip()
    else:
        val = raw
    val = val.strip().lower()
    if val in ("local", "fal"):
        set_chat_state(db, chat_id, "comfyui_provider", val)
        return (
            f"Proveedor visual establecido en '{val}' para esta sesion.\n"
            + provider_status_message(val)  # type: ignore[arg-type]
        )
    if not val:
        cur = resolve_visual_provider(db, chat_id)
        return (
            "Uso: /comfyui --provider local|fal\n"
            + provider_status_message(cur)
            + f"\nDefault sin override: {default_visual_provider()}"
        )
    return "Uso: /comfyui --provider local|fal"


def execute_sandbox_toggle(db: Any, chat_id: Any, on_off: str) -> str:
    """/sandbox on|off: habilita/deshabilita ejecución de código para este chat (por `agent_config`)."""
    v = (on_off or "").strip().lower()

    def _parse(v_: str) -> Optional[bool]:
        vv = (v_ or "").strip().lower()
        if vv in ("on", "1", "true", "sí", "si"):
            return True
        if vv in ("off", "0", "false"):
            return False
        return None

    parsed = _parse(v)
    if parsed is True:
        set_chat_state(db, chat_id, "sandbox_enabled", "true")
        db_path = getattr(db, "_path", None) or getattr(db, "path", None) or "(unknown_db_path)"
        # Warning para asegurar que aparezca en logs de pm2.
        import logging
        logging.getLogger(__name__).warning(
            "[sandbox-toggle] db_path=%r chat_id=%r sandbox_enabled=%r",
            db_path,
            chat_id,
            "true",
        )
        return "Entendido. He habilitado mis capacidades de ejecución de código para esta sesión."
    if parsed is False:
        set_chat_state(db, chat_id, "sandbox_enabled", "false")
        db_path = getattr(db, "_path", None) or getattr(db, "path", None) or "(unknown_db_path)"
        import logging
        logging.getLogger(__name__).warning(
            "[sandbox-toggle] db_path=%r chat_id=%r sandbox_enabled=%r",
            db_path,
            chat_id,
            "false",
        )
        return "Entendido. He desactivado mis capacidades de ejecución de código para esta sesión."

    # Sin args válidos: mostrar estado actual.
    current = _parse(get_chat_state(db, chat_id, "sandbox_enabled"))
    status = "habilitado" if current is True else "desactivado"  # default OFF
    return f"Uso: /sandbox on|off\nEstado actual: {status}."


def execute_internet_toggle(
    db: Any,
    chat_id: Any,
    on_off: str,
    *,
    worker_id: str = "",
    tenant_id: str = "default",
) -> str:
    """/internet on|off: red del sandbox Strix por chat (solo si el worker permite red en YAML)."""
    from duckclaw.forge.schema import resolve_sandbox_network_policy

    v = (on_off or "").strip().lower()
    wid = (worker_id or "").strip()
    if not wid:
        try:
            team = get_effective_team_templates(db, chat_id, str(tenant_id or "default").strip() or "default", None)
            wid = (team[0] if team else "").strip()
        except Exception:
            wid = ""
    if not wid:
        wid = "default"

    _, meta = resolve_sandbox_network_policy(
        wid, get_chat_state(db, chat_id, "sandbox_network_enabled")
    )
    if not meta.get("toggle_available"):
        return (
            f"Este worker («{wid}») tiene red sandbox denegada en security_policy.yaml. "
            "No se puede activar internet desde el chat. Usa tavily_search o un worker con browser_sandbox "
            "habilitado por capability/policy."
        )

    def _parse(v_: str) -> bool | None:
        vv = (v_ or "").strip().lower()
        if vv in ("on", "1", "true", "sí", "si"):
            return True
        if vv in ("off", "0", "false"):
            return False
        return None

    parsed = _parse(v)
    if parsed is True:
        ok, err = set_chat_state_via_vault(db, chat_id, "sandbox_network_enabled", "true", tenant_id=tenant_id)
        if not ok:
            return f"No se pudo guardar: {err}"
        try:
            from duckclaw.graphs.sandbox import cleanup_sandbox_session_for_chat

            cleanup_sandbox_session_for_chat(str(chat_id))
        except Exception:
            pass
        return (
            "Internet en sandbox activado para esta sesión. "
            "El próximo run_sandbox/run_browser_sandbox usará red bridge."
        )
    if parsed is False:
        ok, err = set_chat_state_via_vault(db, chat_id, "sandbox_network_enabled", "false", tenant_id=tenant_id)
        if not ok:
            return f"No se pudo guardar: {err}"
        try:
            from duckclaw.graphs.sandbox import cleanup_sandbox_session_for_chat

            cleanup_sandbox_session_for_chat(str(chat_id))
        except Exception:
            pass
        return "Internet en sandbox desactivado (network_mode=none) para esta sesión."

    eff = meta.get("effective") or "deny"
    return f"Uso: /internet on|off\nRed sandbox efectiva: {eff} (worker {wid})."


def execute_heartbeat(db: Any, chat_id: Any, on_off: str, *, tenant_id: Any = None) -> str:
    """/heartbeat on|off — DM proactivos (Bot API nativa o webhook) mientras el agente usa herramientas."""
    from duckclaw.graphs.chat_heartbeat import (
        heartbeat_outbound_configured,
        heartbeat_redis_configured,
        is_admin_ui_chat_session,
        is_chat_heartbeat_enabled,
        set_chat_heartbeat_enabled,
    )

    tid = str(tenant_id or "default").strip() or "default"
    cid = str(chat_id if chat_id is not None else "unknown").strip() or "unknown"
    v = (on_off or "").strip().lower()

    if not heartbeat_redis_configured():
        return (
            "Heartbeat requiere Redis (REDIS_URL o DUCKCLAW_REDIS_URL). Sin eso no se puede guardar el estado."
        

        )
    if v in ("on", "1", "true", "sí", "si"):
        if is_chat_heartbeat_enabled(tid, cid):
            return "✅ Heartbeat ya estaba activado."
        ok, err = set_chat_heartbeat_enabled(tid, cid, True)
        if not ok:
            return f"No se pudo activar heartbeat: {err}"
        if is_admin_ui_chat_session(cid):
            return "✅ Heartbeat activado. Verás plan y herramientas en este chat mientras ejecuto la tarea."
        if not heartbeat_outbound_configured():
            return (
                "Heartbeat activado en Redis, pero falta TELEGRAM_BOT_TOKEN (recomendado) o un webhook "
                "(TELEGRAM_BOT_TOKEN o DUCKCLAW_HEARTBEAT_WEBHOOK_URL); no se enviarán DMs."
            )
        return "✅ Heartbeat activado. Te avisaré por DM mientras uso herramientas."
    if v in ("off", "0", "false"):
        if not is_chat_heartbeat_enabled(tid, cid):
            return "Heartbeat ya estaba desactivado."
        ok, err = set_chat_heartbeat_enabled(tid, cid, False)
        if not ok:
            return f"No se pudo desactivar heartbeat: {err}"
        return "✅ Heartbeat desactivado."

    st = "on" if is_chat_heartbeat_enabled(tid, cid) else "off"
    return f"Heartbeat: {st}\nUso: /heartbeat on | /heartbeat off"


def execute_audit(db: Any, chat_id: Any) -> str:
    """/audit: evidencia de la última ejecución (SQL, latencia, run_id)."""
    raw = get_chat_state(db, chat_id, "last_audit")
    if not raw:
        return "No hay evidencia de última ejecución. Envía un mensaje y vuelve a usar /audit."
    try:
        data = json.loads(raw)
        sql = data.get("sql") or "(no registrado)"
        latency_ms = data.get("latency_ms") or "—"
        tokens = data.get("tokens") or "—"
        run_id = data.get("run_id") or "—"
        return (
            f"📋 Última ejecución\nSQL: {str(sql)[:300]}\nLatencia: {latency_ms} ms\nTokens: {tokens}\nLangSmith run_id: {run_id}"
        
        )
    except Exception:
        return "Datos de auditoría no válidos."


def execute_health(db: Any) -> str:
    """/health: estado de infraestructura (MLX, DuckDB, latencia)."""
    lines = []
    # DuckDB
    try:
        db.query("SELECT 1")
        lines.append("✅ DuckDB: conectado")
    except Exception as e:
        lines.append(f"❌ DuckDB: {e}")
    # MLX / inference
    base_url = os.environ.get("DUCKCLAW_LLM_BASE_URL", "").strip() or "http://127.0.0.1:8080"
    if base_url:
        base = base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        url = base + "/health"
        try:
            import urllib.request
            t0 = time.perf_counter()
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                elapsed = int((time.perf_counter() - t0) * 1000)
                lines.append(f"✅ Inferencia ({url[:40]}...): {elapsed} ms")
        except Exception as e:
            lines.append(f"⚠️ Inferencia: {e}")
    return "\n".join(lines) or "Sin comprobaciones."


def execute_approve_reject(db: Any, chat_id: Any, approved: bool) -> str:
    """/approve o /reject: HITL (grafo en interrupt). Sin interrupt implementado: mensaje informativo."""
    return "No hay operación pendiente de aprobación. (El grafo no está en estado interrupt en esta versión.)"


def execute_tasks(db: Any, chat_id: Any) -> str:
    """/tasks: estado del ActivityManager (Redis): IDLE, BUSY, subagente, tarea actual, tiempo en ejecución."""
    from duckclaw.graphs.activity import get_activity
    data = get_activity(chat_id)
    if data is None:
        return "⏸ IDLE (Redis no configurado)."
    status = data.get("status", "IDLE")
    task = data.get("task", "")
    worker_id = data.get("worker_id", "") or ""
    started_at = data.get("started_at", 0)
    elapsed_s = ""
    if started_at and status == "BUSY":
        try:
            elapsed_s = f" · {int(time.time()) - int(started_at)}s"
        except Exception:
            pass
    # Guión en worker_id (p. ej. SIATA-Analyst) obliga a \- en MarkdownV2; muchos clientes muestran el \ literal.
    # Mismo criterio que label de gateway: espacio en lugar de guion para etiqueta legible sin escapes.
    worker_display = (worker_id or "").replace("-", " ").strip()
    worker_s = f" · {worker_display}" if worker_display else ""
    # Segunda línea: solo el título del plan (task), precedido por un bullet grande
    task_preview = f"• {str(task)[:60]}" if task else "—"
    icon = "▶" if status == "BUSY" else "⏸"
    return f"{icon} {status}{elapsed_s}{worker_s}\n" + task_preview


def get_effective_system_prompt(db: Any, worker_id: Optional[str] = None) -> str:
    """
    Devuelve el system prompt efectivo para un worker:
    - Si worker_id está definido: 1) override system_prompt_<worker_id>, 2) soul.md + system_prompt.md del template (ver load_system_prompt). No usa global.
    - Si worker_id vacío: global system_prompt o "".
    """
    wid = (worker_id or "").strip()
    if wid:
        override = _get_global_config(db, f"system_prompt_{wid}")
        if override:
            return override
        try:
            from duckclaw.workers.manifest import load_manifest
            from duckclaw.workers.loader import load_system_prompt
            spec = load_manifest(wid)
            return (load_system_prompt(spec) or "").strip()
        except Exception:
            pass
        return ""
    current = _get_global_config(db, "system_prompt")
    return current if current else ""


_PROVIDERS = ("mlx", "ollama", "openai", "anthropic", "deepseek", "groq", "gemini", "openrouter", "or")

# Modelo por defecto al cambiar provider (evita "Model Not Exist" al pasar de MLX a cloud)
_DEFAULT_MODEL_BY_PROVIDER = {
    "deepseek": "deepseek-chat",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-2.0-flash",
    "openrouter": "deepseek/deepseek-v4-flash",
    "mlx": "",  # usa MLX_MODEL_ID o /v1/models
    "ollama": "llama3.2",
}

# Base URL por defecto al cambiar provider (evita mezclar host global PM2 con otro proveedor).
_DEFAULT_BASE_URL_BY_PROVIDER = {
    "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "",
    "anthropic": "",
    "gemini": "",
    "mlx": "",
    "ollama": "http://127.0.0.1:11434",
}


def _effective_llm_triplet_for_chat_ui(db: Any, chat_id: Any) -> tuple[str, str, str]:
    """provider/model/base_url efectivos (chat > global agent_config > env), con MLX forzado a host local."""
    from duckclaw.integrations.llm_providers import (
        _ensure_duckclaw_llm_env_from_legacy_llm_vars,
        mlx_openai_compatible_base_url,
    )

    _ensure_duckclaw_llm_env_from_legacy_llm_vars()
    p_chat = (get_chat_state(db, chat_id, "llm_provider") or "").strip()
    p_global = (_get_global_config(db, "llm_provider") or "").strip()
    p_env = (os.environ.get("DUCKCLAW_LLM_PROVIDER", "mlx") or "").strip()
    p = (p_chat or p_global or p_env).strip().lower()
    m_chat = (get_chat_state(db, chat_id, "llm_model") or "").strip()
    m_global = (_get_global_config(db, "llm_model") or "").strip()
    m_env = (os.environ.get("DUCKCLAW_LLM_MODEL", "") or "").strip()
    m = (m_chat or m_global or m_env).strip()
    u_chat = (get_chat_state(db, chat_id, "llm_base_url") or "").strip()
    u_global = (_get_global_config(db, "llm_base_url") or "").strip()
    u_env = (os.environ.get("DUCKCLAW_LLM_BASE_URL", "") or "").strip()
    u = (u_chat or u_global or u_env).strip()
    if p == "mlx":
        ul = u.lower()
        if (not u) or "groq.com" in ul or "deepseek.com" in ul:
            u = mlx_openai_compatible_base_url()
        if not m:
            m = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
    _debug_log_model_config(
        hypothesis_id="H_sources_priority",
        location="on_the_fly_commands._effective_llm_triplet_for_chat_ui",
        message="effective_triplet_computed",
        data={
            "chat_id": str(chat_id),
            "provider": p,
            "model": m[:80],
            "base_url": u[:120],
            "src_provider": "chat" if p_chat else ("global" if p_global else "env"),
            "src_model": "chat" if m_chat else ("global" if m_global else "env"),
            "src_base_url": "chat" if u_chat else ("global" if u_global else "env"),
            "chat_provider": p_chat[:60],
            "chat_base_url": u_chat[:120],
            "global_provider": p_global[:60],
            "global_base_url": u_global[:120],
            "env_provider": p_env[:60],
            "env_base_url": u_env[:120],
        },
    )
    return (p, m, u)


_configure_goals_llm_triplet_resolver(_effective_llm_triplet_for_chat_ui)


def chat_has_llm_chat_state_override(db: Any, chat_id: Any) -> bool:
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    for key in ("llm_provider", "llm_model", "llm_base_url"):
        if (get_chat_state(db, cid, key) or "").strip():
            return True
    return False


def resolve_llm_triplet_for_chat_invocation(db: Any, chat_id: Any) -> tuple[str, str, str] | None:
    """Si el chat tiene llm_* en agent_config, devuelve tripleta para build_llm; si no, None (usar cache env del gateway)."""
    has_override = chat_has_llm_chat_state_override(db, chat_id)
    _debug_log_model_config(
        hypothesis_id="H_override_gate",
        location="on_the_fly_commands.resolve_llm_triplet_for_chat_invocation",
        message="chat_override_gate",
        data={"chat_id": str(chat_id), "has_override": bool(has_override)},
    )
    if not has_override:
        return None
    return _effective_llm_triplet_for_chat_ui(db, chat_id)


def execute_model(db: Any, chat_id: Any, args: str) -> str:
    """/model [provider=mlx] [model=...] [base_url=...]: cambia proveedor/modelo LLM en caliente. Sin args muestra el actual."""
    _debug_log_model_config(
        hypothesis_id="H_write_apply",
        location="on_the_fly_commands.execute_model",
        message="execute_model_entry",
        data={"chat_id": str(chat_id), "args": (args or "")[:180]},
    )
    if not args or not args.strip():
        provider, model, base_url = _effective_llm_triplet_for_chat_ui(db, chat_id)
        provider = provider or "—"
        model = model or "—"
        u_show = base_url or "—"
        base_url = u_show[:50] + "…" if len(u_show) > 50 else u_show
        return f"Modelo actual:\n- provider: {provider}\n- model: {model}\n- base_url: {base_url}\n\nUso: /model provider=mlx | /model provider=deepseek | /model provider=openrouter | /model provider=or model=google/gemini-2.5-pro | /model model=Slayer-8B"
    for part in args.split("|"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k == "provider":
                if v and v.lower() not in _PROVIDERS:
                    return f"Provider desconocido: {v}. Válidos: {', '.join(_PROVIDERS)}"
                pv = v.lower()
                if pv in ("or", "router"):
                    pv = "openrouter"
                set_chat_state(db, chat_id, "llm_provider", pv)
                # Al cambiar provider, resetear model al default para evitar "Model Not Exist"
                # (ej. Slayer-8B-v1.1 no existe en DeepSeak)
                if pv == "mlx":
                    from duckclaw.integrations.llm_providers import mlx_openai_compatible_base_url

                    set_chat_state(db, chat_id, "llm_base_url", mlx_openai_compatible_base_url())
                    mid = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
                    set_chat_state(db, chat_id, "llm_model", mid)
                else:
                    default_model = _DEFAULT_MODEL_BY_PROVIDER.get(pv, "")
                    set_chat_state(db, chat_id, "llm_model", default_model)
                    default_url = _DEFAULT_BASE_URL_BY_PROVIDER.get(pv, "")
                    if default_url:
                        set_chat_state(db, chat_id, "llm_base_url", default_url)
                    else:
                        set_chat_state(db, chat_id, "llm_base_url", "")
                _debug_log_model_config(
                    hypothesis_id="H_write_apply",
                    location="on_the_fly_commands.execute_model",
                    message="provider_written",
                    data={
                        "chat_id": str(chat_id),
                        "provider_arg": pv,
                        "default_model": (_DEFAULT_MODEL_BY_PROVIDER.get(pv, "") or "")[:80],
                        "default_base_url": (_DEFAULT_BASE_URL_BY_PROVIDER.get(pv, "") or "")[:120],
                    },
                )
            elif k == "model":
                set_chat_state(db, chat_id, "llm_model", v)
            elif k == "base_url":
                set_chat_state(db, chat_id, "llm_base_url", v)
    _p, _m, _u = _effective_llm_triplet_for_chat_ui(db, chat_id)
    _debug_log_model_config(
        hypothesis_id="H_write_apply",
        location="on_the_fly_commands.execute_model",
        message="execute_model_exit",
        data={"chat_id": str(chat_id), "provider": _p, "model": _m[:80], "base_url": _u[:120]},
    )
    return "✅ Modelo actualizado. Los próximos mensajes usarán esta config."


def _parse_pipe_kv_args(args: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (args or "").split("|"):
        p = part.strip()
        if "=" not in p:
            continue
        k, _, v = p.partition("=")
        k = k.strip().lower()
        v = v.strip()
        if k:
            out[k] = v
    return out


def _gemini_models_list_from_api(api_key: str) -> tuple[list[str], str | None]:
    url = "https://generativelanguage.googleapis.com/v1beta/models"
    req = urllib.request.Request(
        f"{url}?key={urllib.parse.quote(api_key)}",
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            status = getattr(resp, "status", 200)
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        return [], f"Gemini API HTTP {e.code}: {(detail or '').strip()[:220] or 'sin detalle'}"
    except Exception as e:
        return [], f"No pude consultar Gemini models: {e}"
    if status < 200 or status >= 300:
        return [], f"Gemini API devolvió HTTP {status}."
    try:
        payload = json.loads(body or "{}")
    except json.JSONDecodeError:
        return [], "Gemini API devolvió una respuesta no-JSON."
    models = payload.get("models")
    if not isinstance(models, list):
        return [], "Gemini API no devolvió la lista de modelos."
    usable: list[str] = []
    for row in models:
        if not isinstance(row, dict):
            continue
        raw_name = str(row.get("name") or "").strip()
        if not raw_name:
            continue
        methods = row.get("supportedGenerationMethods") or []
        if isinstance(methods, list) and methods:
            method_names = {str(m).strip() for m in methods if str(m).strip()}
            if "generateContent" not in method_names:
                continue
        short_name = raw_name.split("/")[-1]
        if short_name:
            usable.append(short_name)
    dedup = sorted(set(usable))
    if "gemini-2.0-flash" in dedup:
        dedup = ["gemini-2.0-flash"] + [m for m in dedup if m != "gemini-2.0-flash"]
    return dedup, None


def execute_models(db: Any, chat_id: Any, args: str) -> str:
    """/models provider=gemini: lista modelos disponibles del proveedor."""
    kv = _parse_pipe_kv_args(args)
    provider = (kv.get("provider") or "").strip().lower()
    if not provider:
        provider = (_effective_llm_triplet_for_chat_ui(db, chat_id)[0] or "").strip().lower()
    if not provider:
        return "Uso: /models provider=gemini"
    if provider != "gemini":
        return "Por ahora /models soporta solo provider=gemini."
    key = ((os.environ.get("GOOGLE_API_KEY") or "").strip() or (os.environ.get("GEMINI_API_KEY") or "").strip())
    if not key:
        return "Falta GOOGLE_API_KEY (o GEMINI_API_KEY) para listar modelos de Gemini."
    models, err = _gemini_models_list_from_api(key)
    if err:
        return f"No se pudo listar modelos Gemini. {err}"
    if not models:
        return "Gemini no devolvió modelos utilizables para generateContent."
    preview = "\n".join(f"- {m}" for m in models[:30])
    more = "" if len(models) <= 30 else f"\n... y {len(models) - 30} más."
    hint = "\nSugerencia: /model provider=gemini | model=gemini-2.0-flash"
    return f"Modelos Gemini disponibles ({len(models)}):\n{preview}{more}{hint}"


def execute_prompt(db: Any, chat_id: Any, args: str) -> str:
    """/prompt <worker_id> [--change <nuevo prompt>]: ver o cambiar el system prompt del template. worker_id debe ser uno de /roles."""
    from duckclaw.workers.factory import list_workers
    all_templates = list_workers()
    raw = (args or "").strip()
    if not raw:
        return "Uso: /prompt <worker_id> [--change <texto>]. Ver templates: /roles"
    if raw.startswith("--"):
        return "Indica un worker_id (ej. research_worker). Ver templates: /roles"
    change_marker = " --change "
    idx = raw.lower().find(change_marker)
    if idx >= 0:
        worker_id = raw[:idx].strip().lower()
        new_prompt = raw[idx + len(change_marker):].strip()
    else:
        worker_id = raw.split()[0].strip().lower() if raw.split() else ""
        new_prompt = ""
    if not worker_id:
        return "Uso: /prompt <worker_id> [--change <texto>]. Ver templates: /roles"
    if worker_id not in all_templates:
        return f"Template '{worker_id}' no encontrado. Disponibles (usa /roles): {', '.join(all_templates)}"
    if new_prompt:
        _set_global_config(db, f"system_prompt_{worker_id}", new_prompt)
        preview = new_prompt[:200] + "..." if len(new_prompt) > 200 else new_prompt
        return f"✅ System prompt de {worker_id} actualizado.\nVista previa: {preview}"
    current = get_effective_system_prompt(db, worker_id)
    if not current:
        return f"System prompt de {worker_id}: (vacío o por defecto del template).\nPara cambiar: /prompt {worker_id} --change <texto>"
    preview = current[:400] + "..." if len(current) > 400 else current
    return f"System prompt de {worker_id}:\n{preview}\n\nPara cambiar: /prompt {worker_id} --change <texto>"


def execute_help(db: Any, chat_id: Any) -> str:
    """/help: lista los fly commands disponibles."""
    entries = list(load_guardrail_pipe_table("fly_commands", "help_entries"))
    block = "\n".join(f"- {cmd} — {desc}" for cmd, desc in entries)
    return f"{load_guardrail('fly_commands', 'help_header')}\n{block}"


def _fly_reply_preview(s: str, max_len: int = 120) -> str:
    """Resumen de respuesta para [FLY] sin volcar secretos ni bloques enormes."""
    t = (s or "").replace("\n", " ").strip()
    if len(t) > max_len:
        return t[:max_len] + "..."
    return t


def _ssh_reach_icon(reach: str) -> str:
    r = (reach or "").lower()
    if "alcanzable" in r and "ok" in r:
        return "✅"
    if "no probado" in r or "falta config" in r:
        return "⚠️"
    return "❌"


def _capadonna_lake_status_lines(*, compact: bool) -> list[str]:
    """Líneas de diagnóstico de conectividad SSH/Tailscale para /lake y /sensors."""
    host = (os.environ.get("CAPADONNA_SSH_HOST") or "").strip()
    user = (os.environ.get("CAPADONNA_SSH_USER") or "capadonna").strip()
    idp = (os.environ.get("CAPADONNA_SSH_IDENTITY_FILE") or "").strip()
    reach = "no probado (falta config)"
    if host:
        ssh_args: list[str] = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
        if idp:
            ssh_args.extend(["-i", idp])
        ssh_args.extend([f"{user}@{host}", "true"])
        try:
            proc = subprocess.run(ssh_args, capture_output=True, text=True, timeout=20)
            if proc.returncode == 0:
                reach = "alcanzable (ssh true OK)"
            else:
                err = (proc.stderr or proc.stdout or "").strip()[:200]
                reach = f"fallo rc={proc.returncode}" + (f" — {err}" if err else "")
        except FileNotFoundError:
            reach = "ssh no encontrado en PATH"
        except subprocess.TimeoutExpired:
            reach = "timeout 20s"
        except Exception as exc:
            reach = str(exc)[:120]
    if compact:
        return [
            "🌊 Lake de datos · SSH / Tailscale",
            f"   {'✅' if host else '⚠️'} Host configurado: {'sí' if host else 'no'}",
            f"   {_ssh_reach_icon(reach)} Alcance SSH (rápido): {reach}",
        ]
    return [
        "Lake de datos (SSH)",
        f"- CAPADONNA_SSH_HOST: {'sí' if host else 'no'}",
        f"- CAPADONNA_SSH_USER: {user}",
        f"- Clave SSH (-i): {idp or '(no definida / ssh-agent)'}",
        f"- Alcance SSH rápido: {reach}",
    ]


def _sensor_line_bullet(icon: str, text: str) -> str:
    """Una línea de detalle bajo un bloque /sensors (icono + texto)."""
    t = (text or "").strip()
    return f"   {icon} {t}" if t else f"   {icon}"


def _browser_sandbox_sensor_lines() -> list[str]:
    """Líneas compactas para /sensors: Docker e imagen browser sandbox."""
    lines: list[str] = [
        "🌐 Browser sandbox · Playwright (`run_browser_sandbox`)",
    ]
    try:
        from duckclaw.graphs.sandbox import _browser_image_name, _docker_available
    except Exception as exc:
        lines.append(_sensor_line_bullet("❌", f"Sandbox no importable — {exc!s}"[:120]))
        return lines

    if not _docker_available():
        lines.append(_sensor_line_bullet("❌", "Docker no responde — run_browser_sandbox no arrancará"))
        return lines

    lines.append(_sensor_line_bullet("✅", "Docker ping OK"))
    img = _browser_image_name()
    env_override = bool((os.environ.get("STRIX_BROWSER_IMAGE") or "").strip())
    label = f"{img}" + (" · STRIX_BROWSER_IMAGE" if env_override else "")
    try:
        import docker  # noqa: PLC0415

        client = docker.from_env()
        client.images.get(img)
        lines.append(_sensor_line_bullet("✅", f"Imagen local · {label}"[:140]))
    except Exception:
        lines.append(
            _sensor_line_bullet(
                "⚠️",
                f"Imagen no encontrada localmente · {label} — build/pull antes del primer uso",
            )[:200]
        )
    return lines


def execute_sensors(db: Any) -> str:
    """/sensors: resumen DuckDB, conectividad, research y browser sandbox."""
    blocks: list[str] = ["📡 Sensores de plataforma", "═══════════════════════", ""]

    try:
        db.query("SELECT 1")
        blocks.append("🦆 DuckDB local")
        blocks.append(_sensor_line_bullet("✅", "Conectado · SELECT 1 OK"))
    except Exception as exc:
        blocks.append("🦆 DuckDB local")
        blocks.append(_sensor_line_bullet("❌", f"Error — {str(exc)[:100]}"))

    blocks.append("")
    try:
        blocks.extend(_capadonna_lake_status_lines(compact=True))
    except Exception as exc:
        blocks.append("🌊 Lake de datos")
        blocks.append(_sensor_line_bullet("❌", f"Error — {str(exc)[:100]}"))

    blocks.append("")
    try:
        from duckclaw.forge.skills.research_bridge import _tavily_available
    except Exception:
        _tavily_available = lambda: False  # type: ignore[misc, assignment]

    tav_pkg = False
    try:
        import tavily  # noqa: F401

        tav_pkg = True
    except ImportError:
        pass
    tav_key = bool((os.environ.get("TAVILY_API_KEY") or "").strip())
    tav_ready = bool(_tavily_available())
    blocks.append("🔎 Tavily (research)")
    if tav_ready and tav_pkg and tav_key:
        blocks.append(_sensor_line_bullet("✅", "Listo · paquete · TAVILY_API_KEY · bridge"))
    elif not tav_pkg and not tav_key:
        blocks.append(_sensor_line_bullet("⚠️", "Sin paquete tavily ni clave"))
    else:
        blocks.append(
            _sensor_line_bullet(
                "⚠️",
                f"Parcial · paquete={'sí' if tav_pkg else 'no'} · clave={'sí' if tav_key else 'no'} · bridge={'sí' if tav_ready else 'no'}",
            )
        )

    blocks.append("")
    try:
        blocks.extend(_browser_sandbox_sensor_lines())
    except Exception as exc:
        blocks.append("🌐 Browser sandbox · Playwright (`run_browser_sandbox`)")
        blocks.append(_sensor_line_bullet("❌", f"Error — {str(exc)[:100]}"))

    return "\n".join(blocks)


def execute_lake_status() -> str:
    """/lake [status]: variables de lake y prueba SSH corta (BatchMode, ConnectTimeout=5)."""
    try:
        lines = _capadonna_lake_status_lines(compact=False)
    except Exception as e:
        return f"Lake: no se pudo leer conectividad: {e}"
    return "\n".join(lines)


def execute_resolve_uncertainty(db: Any, chat_id: Any, args: str, *, tenant_id: Any = None) -> str:
    """/resolve_uncertainty <event_uuid>: cierra PENDING_HITL y reactiva sesión si no quedan dudas."""
    eid = (args or "").strip().lower().split()[0] if (args or "").strip() else ""
    if not re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        eid,
    ):
        return "Uso: /resolve_uncertainty <event_id_UUID>"
    try:
        from duckclaw.capadonna_plugin import load_capadonna_lib

        bridge = load_capadonna_lib("epistemic_humility_bridge")
        if bridge is None:
            return "Capadonna epistemic_humility_bridge no disponible."
        tid = str(tenant_id or get_chat_state(db, chat_id, "tenant_id") or "default").strip() or "default"
        uid = str(get_chat_state(db, chat_id, "last_requester_id") or tid).strip() or tid
        result = bridge.resolve_uncertainty_event(db, event_id=eid, tenant_id=tid, user_id=uid)
        if result.get("error"):
            return f"No: {result['error']}"
        return (
            f"Incertidumbre resuelta. event_id={result.get('event_id')} "
            f"session_uid={result.get('session_uid')}"
        )
    except Exception as exc:
        return f"Error al resolver incertidumbre: {exc}"


def execute_uncertainty_status(db: Any, chat_id: Any, args: str) -> str:
    """/uncertainty --status: lista eventos PENDING_HITL de la sesión activa."""
    _ = chat_id, args
    try:
        from duckclaw.capadonna_plugin import load_capadonna_lib

        bridge = load_capadonna_lib("epistemic_humility_bridge")
        if bridge is None:
            return "Capadonna epistemic_humility_bridge no disponible."
        rows = bridge.list_pending_uncertainty_events(db, limit=10)
        if not rows:
            return "Sin eventos de incertidumbre PENDING_HITL en la sesión activa."
        lines = ["**Incertidumbre pendiente (HITL)**"]
        for row in rows:
            lines.append(
                f"- `{row.get('id')}` · {row.get('trigger_context')} · C={row.get('confidence_score')}"
            )
        lines.append("\nResuelve con `/resolve_uncertainty <event_id>`.")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error listando incertidumbre: {exc}"


def execute_code_approve(db: Any, chat_id: Any, args: str) -> str:
    """/approve-code <uuid>: HITL para code_decisions."""
    decision_id = (args or "").strip().lower().split()[0] if (args or "").strip() else ""
    if not re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        decision_id,
    ):
        return "Uso: /approve-code <decision_id_UUID>"
    try:
        from duckclaw.forge.code_decision_service import approve_code_decision

        tenant = str(get_chat_state(db, chat_id, "tenant_id") or "default").strip() or "default"
        user_id = str(get_chat_state(db, chat_id, "last_requester_id") or tenant).strip() or tenant
        result = approve_code_decision(
            db,
            decision_id=decision_id,
            tenant_id=tenant,
            user_id=user_id,
            chat_id=str(chat_id).strip(),
        )
        if result.get("error"):
            return f"No: {result['error']}"
        pr_url = result.get("pr_url") or ""
        return f"Código aprobado. decision_id={decision_id}. PR: {pr_url or 'ver GitHub Actions'}."
    except Exception as exc:
        return f"Error al aprobar code_decision: {exc}"


def execute_code_reject(db: Any, chat_id: Any, args: str) -> str:
    """/reject-code <uuid> [razón]: rechaza code_decision."""
    parts = (args or "").strip().split(maxsplit=1)
    decision_id = (parts[0] if parts else "").strip().lower()
    rationale = parts[1] if len(parts) > 1 else ""
    if not re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        decision_id,
    ):
        return "Uso: /reject-code <decision_id_UUID> [razón]"
    try:
        from duckclaw.forge.code_decision_service import reject_code_decision

        tenant = str(get_chat_state(db, chat_id, "tenant_id") or "default").strip() or "default"
        user_id = str(get_chat_state(db, chat_id, "last_requester_id") or tenant).strip() or tenant
        result = reject_code_decision(
            db,
            decision_id=decision_id,
            tenant_id=tenant,
            user_id=user_id,
            rationale=rationale,
        )
        return f"Decisión {decision_id} → {result.get('status', 'REJECTED')}."
    except Exception as exc:
        return f"Error al rechazar: {exc}"


def _dispatch_fly_command(
    db: Any,
    chat_id: Any,
    name: str,
    args: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
    vault_user_id: Any = None,
    username: str = "",
    entry_worker_id: str | None = None,
) -> Optional[str]:
    """Ejecuta un comando fly ya parseado (sin contexto de logging)."""
    if name == "sensors":
        return execute_sensors(db)
    if name == "lake":
        sub = (args or "").strip().lower()
        if sub in ("", "status"):
            return execute_lake_status()
        return "Uso: /lake o /lake status"
    if name in ("resolve_uncertainty", "resolve-uncertainty"):
        return execute_resolve_uncertainty(db, chat_id, args, tenant_id=tenant_id)
    if name == "uncertainty":
        sub = (args or "").strip().lower()
        if sub in ("--status", "status", ""):
            return execute_uncertainty_status(db, chat_id, args)
        return "Uso: /uncertainty --status"
    if name in ("approve_code", "approve-code"):
        return execute_code_approve(db, chat_id, args)
    if name in ("reject_code", "reject-code"):
        return execute_code_reject(db, chat_id, args)
    if name == "help":
        return execute_help(db, chat_id)
    if name == "role":
        return (
            "El comando /role ya no existe. Usa /workers para ver o definir el equipo, /help para ver todos los comandos."
        
        )
    if name == "roles":
        return execute_roles(db, chat_id)
    if name == "team":
        return execute_team_whitelist(db, tenant_id, requester_id, args)
    if name == "vault":
        return execute_vault(
            args,
            vault_user_id=vault_user_id or requester_id or chat_id,
            tenant_id=tenant_id,
            db=db,
            entry_worker_id=entry_worker_id,
            chat_id=chat_id,
            worker_id_resolver=get_worker_id_for_chat,
        )
    if name == "workers":
        return execute_team(
            db, chat_id, args, tenant_id=tenant_id, requester_id=requester_id
        )
    if name == "skills":
        return execute_skills_list(db, chat_id, args)
    if name == "forget":
        return execute_forget(db, chat_id)
    if name == "context":
        return execute_context_toggle(db, chat_id, args)
    if name == "comfyui":
        return execute_comfyui_provider(db, chat_id, args)
    if name in ("sandbox", "sandox"):
        return execute_sandbox_toggle(db, chat_id, args)
    if name in ("internet", "red", "network"):
        return execute_internet_toggle(db, chat_id, args, tenant_id=tenant_id)
    if name == "heartbeat":
        return execute_heartbeat(db, chat_id, args, tenant_id=tenant_id)
    if name == "audit":
        return execute_audit(db, chat_id)
    if name == "health":
        return execute_health(db)
    if name == "approve":
        return execute_approve_reject(db, chat_id, True)
    if name == "reject":
        return execute_approve_reject(db, chat_id, False)
    if name in ("prompt", "system_prompt", "system"):
        return execute_prompt(db, chat_id, args)
    if name in ("model", "provider", "llm"):
        return execute_model(db, chat_id, args)
    if name in ("models",):
        return execute_models(db, chat_id, args)
    if name == "setup":
        return _execute_setup(db, chat_id, args)
    if name == "goals":
        return execute_homeostasis_goals(
            db,
            chat_id,
            args,
            tenant_id=tenant_id,
            vault_user_id=vault_user_id,
        )
    if name == "crons":
        return execute_crons_schedule(
            db,
            chat_id,
            args,
            tenant_id=tenant_id,
            vault_user_id=vault_user_id,
        )
    if name == "meditate":
        args_norm = (args or "").strip().lower()
        if args_norm in ("--self", "--now"):
            return None
        return execute_meditate(
            db, chat_id, args, tenant_id=tenant_id, vault_user_id=vault_user_id
        )
    if name == "tasks":
        return execute_tasks(db, chat_id)
    if name == "history":
        return execute_history(db, chat_id, args)
    return None




def handle_command(
    db: Any,
    chat_id: Any,
    text: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
    vault_user_id: Any = None,
    username: str = "",
    entry_worker_id: str | None = None,
) -> Optional[str]:
    """
    Middleware: si el mensaje es un comando on-the-fly, ejecuta y retorna la respuesta.
    Si no es comando o no es manejado, retorna None.
    """
    name, args = parse_command(text)
    if not name:
        return None
    tid = str(tenant_id or "default").strip() or "default"
    try:
        cid = str(chat_id if chat_id is not None else "unknown").strip() or "unknown"
    except Exception:
        cid = "unknown"
    uname = (username or "").strip()
    if not uname and db is not None:
        try:
            uname = str(get_chat_state(db, chat_id, "username") or "").strip()
        except Exception:
            uname = ""
    chat_ident = format_chat_log_identity(cid, uname or None)
    _fly_log = get_obs_logger("duckclaw.fly")
    with structured_log_context(tenant_id=tid, worker_id="gateway", chat_id=chat_ident):
        try:
            set_chat_state(db, chat_id, "tenant_id", tid)
            if requester_id is not None:
                set_chat_state(db, chat_id, "last_requester_id", str(requester_id).strip())
        except Exception:
            pass
        ew = (entry_worker_id or "").strip()
        if ew and ew.lower() != "manager" and db is not None:
            try:
                from duckclaw.workers.factory import list_workers

                canonical = _resolve_template_id(list_workers(), ew)
                if canonical:
                    set_chat_state(db, chat_id, "worker_id", canonical)
                    _crons_debug_log(
                        "on_the_fly_commands.py:handle_command",
                        "entry_worker_synced",
                        {"chat_id": cid, "worker_id": canonical},
                        hypothesis_id="B",
                    )
            except Exception:
                pass
        out = _dispatch_fly_command(
            db,
            chat_id,
            name,
            args,
            requester_id=requester_id,
            tenant_id=tenant_id,
            vault_user_id=vault_user_id,
            username=username or "",
            entry_worker_id=entry_worker_id,
        )
        if out is not None:
            log_fly(_fly_log, "/%s -> %s", name, _fly_reply_preview(out))
        return out


def _execute_setup(db: Any, chat_id: Any, args: str) -> str:
    """/setup [key=value | key=value]: formato compatible con Telegram. Sin args muestra config."""
    if not args or not args.strip():
        p = get_chat_state(db, chat_id, "llm_provider") or _get_global_config(db, "llm_provider")
        m = get_chat_state(db, chat_id, "llm_model") or _get_global_config(db, "llm_model")
        wid = get_chat_state(db, chat_id, "worker_id")
        prompt = _get_global_config(db, "system_prompt") or ""
        return (
            f"Config actual:\n- llm_provider: {p or '—'}\n- llm_model: {m or '—'}\n"
            f"- worker_id: {wid or '—'}\n- system_prompt: {prompt[:80]}...\n\n"
            "Para cambiar: /setup llm_provider=deepseek | /setup system_prompt=..."
        
        )
    for part in args.split("|"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k in ("llm_provider", "provider"):
                if v and v.lower() not in _PROVIDERS:
                    return f"Provider desconocido: {v}. Válidos: {', '.join(_PROVIDERS)}"
                set_chat_state(db, chat_id, "llm_provider", v)
                if v.lower() == "mlx":
                    from duckclaw.integrations.llm_providers import mlx_openai_compatible_base_url

                    set_chat_state(db, chat_id, "llm_base_url", mlx_openai_compatible_base_url())
                    mid = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
                    set_chat_state(db, chat_id, "llm_model", mid)
                else:
                    default_model = _DEFAULT_MODEL_BY_PROVIDER.get(v.lower(), "")
                    set_chat_state(db, chat_id, "llm_model", default_model)
                    default_url = _DEFAULT_BASE_URL_BY_PROVIDER.get(v.lower(), "")
                    if default_url:
                        set_chat_state(db, chat_id, "llm_base_url", default_url)
                    else:
                        set_chat_state(db, chat_id, "llm_base_url", "")
            elif k in ("llm_model", "model"):
                set_chat_state(db, chat_id, "llm_model", v)
            elif k in ("llm_base_url", "base_url"):
                set_chat_state(db, chat_id, "llm_base_url", v)
            elif k in ("system_prompt", "prompt"):
                _set_global_config(db, "system_prompt", v)
    return "✅ Config actualizado."


def get_history_limit_for_chat(db: Any, chat_id: Any, default: int = 10) -> int:
    """Devuelve el límite de historial según use_rag del chat (para /context off = menos contexto)."""
    use_rag = get_chat_state(db, chat_id, "use_rag")
    if use_rag == "false":
        return 3
    return default


def get_worker_id_for_chat(db: Any, chat_id: Any) -> str:
    """Devuelve el worker_id asignado a este chat. Por defecto: manager (orquesta y delega a templates)."""
    return get_chat_state(db, chat_id, "worker_id") or _DEFAULT_WORKER


def save_last_audit(db: Any, chat_id: Any, latency_ms: int, sql: str = "", run_id: str = "", tokens: Any = None) -> None:
    """Guarda datos de la última ejecución para /audit."""
    data = {"latency_ms": latency_ms, "sql": sql or "", "run_id": run_id or "", "tokens": tokens or ""}
    set_chat_state(db, chat_id, "last_audit", json.dumps(data))


_TASK_AUDIT_TABLE = "task_audit_log"


def _ensure_task_audit_log(db: Any) -> None:
    """Crea task_audit_log y aplica migraciones suaves (plan_title)."""
    if _skip_runtime_ddl(db):
        return
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TASK_AUDIT_TABLE} (
            task_id VARCHAR PRIMARY KEY,
            tenant_id VARCHAR NOT NULL,
            worker_id VARCHAR,
            query_prefix VARCHAR,
            status VARCHAR NOT NULL,
            duration_ms INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            plan_title VARCHAR
        )
        """
    )
    # Migración suave: añadir plan_title si la tabla existe sin esta columna (bases antiguas)
    try:
        info = db.query(f"PRAGMA table_info({_TASK_AUDIT_TABLE})")
        rows = json.loads(info) if isinstance(info, str) else (info or [])
        cols = {str(r.get("name") or "") for r in rows if isinstance(r, dict)}
        if "plan_title" not in cols:
            db.execute(f"ALTER TABLE {_TASK_AUDIT_TABLE} ADD COLUMN plan_title VARCHAR")
    except Exception:
        # No romper si PRAGMA/ALTER falla; la feature seguirá funcionando sin plan_title persistente.
        pass


def _infer_user_id_for_audit_queue(db_path: str) -> str:
    """Alineado con validate_user_db_path: slug bajo db/private/{user}/."""
    from pathlib import Path

    parts = Path(db_path).expanduser().resolve().parts
    if "private" in parts:
        i = parts.index("private")
        if i + 1 < len(parts):
            return str(parts[i + 1])
    return "default"


def append_task_audit(
    db: Any,
    tenant_id: Any,
    worker_id: str,
    query_prefix: str,
    status: str,
    duration_ms: int,
    plan_title: Optional[str] = None,
) -> None:
    """Append a task to task_audit_log for /history. plan_title es el identificador semántico para auditoría y /history."""
    import uuid

    _ensure_task_audit_log(db)
    task_id = f"TASK-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    tenant_s = str(tenant_id).replace("'", "''")[:128]
    worker_s = (worker_id or "").replace("'", "''")[:64]
    prefix_s = (query_prefix or "")[:256].replace("'", "''")
    status_s = (status or "SUCCESS").upper().replace("'", "''")[:32]
    status_allowed = ("SUCCESS", "FAILED", "PROACTIVE_MESSAGE_SENT", "SECURITY_VIOLATION_ATTEMPT")
    status_s = "SUCCESS" if status_s not in status_allowed else status_s
    plan_title_s = (plan_title or "")[:256].replace("'", "''") if plan_title else ""
    sql = (
        f"""
        INSERT INTO {_TASK_AUDIT_TABLE} (task_id, tenant_id, worker_id, query_prefix, status, duration_ms, plan_title)
        VALUES ('{task_id}', '{tenant_s}', '{worker_s}', '{prefix_s}', '{status_s}', {int(duration_ms)}, '{plan_title_s}')
        """
    )
    if _skip_runtime_ddl(db):
        try:
            from pathlib import Path

            from duckclaw.db_write_queue import enqueue_duckdb_write_sync, poll_task_status_sync

            raw_path = str(getattr(db, "_path", "") or "").strip()
            if not raw_path or raw_path == ":memory:":
                return
            resolved = str(Path(raw_path).expanduser().resolve())
            uid = _infer_user_id_for_audit_queue(resolved)
            # El manager RO mantiene ``duckdb.connect`` al vault: db-writer no puede tomar RW
            # hasta suspender el handle (mismo patrón que ``admin_sql`` para workers RO).
            released_ro = False
            try:
                release = getattr(db, "release_file_handle_for_external_writer", None)
                susp = getattr(db, "suspend_readonly_file_handle", None)
                resu = getattr(db, "resume_readonly_file_handle", None)
                if callable(release):
                    release()
                    released_ro = bool(callable(resu))
                elif callable(susp) and callable(resu):
                    susp()
                    released_ro = True
                write_tid = enqueue_duckdb_write_sync(
                    db_path=resolved,
                    query=sql.strip(),
                    user_id=uid,
                    tenant_id=str(tenant_id or "default").strip() or "default",
                )
                poll_task_status_sync(write_tid, timeout_sec=15.0)
            finally:
                if released_ro:
                    try:
                        resu2 = getattr(db, "resume_readonly_file_handle", None)
                        if callable(resu2):
                            resu2()
                    except Exception:
                        pass
        except Exception:
            pass
        return
    db.execute(sql)


def _is_simple_greeting(prefix: str) -> bool:
    """True si el mensaje es un saludo corto (hola, hi, etc.) sin tarea real."""
    p = (prefix or "").strip().lower()[:50]
    if len(p) > 35:
        return False
    greetings = (
        "hola", "hi", "hey", "hello", "buenas", "qué tal", "que tal",
        "buenos días", "buenos dias", "buenas tardes", "buenas noches",
        "ola", "saludos", "ciao", "adios", "chao",
    )
    return p in greetings or p.rstrip("!?.") in greetings


_CAPABILITIES_SMALLTALK = re.compile(
    r"""^[\s¿¡]*(
  qu[eé]\s+puedes\s+hacer(\s+ahora|\s+por\s+m[ií]|\s+por\s+nosotros)? |
  qu[eé]\s+sabes\s+hacer |
  en\s+qu[eé]\s+puedes\s+ayud(ar|arme) |
  qu[eé]\s+puedes\s+ofrec(er|erme) |
  cu[aá]les\s+son\s+tus\s+capacidades |
  para\s+qu[eé]\s+sirves |
  qu[eé]\s+funciones\s+tienes |
  mu[eé]strame\s+qu[eé]\s+puedes(\s+hacer)? |
  what\s+can\s+you\s+do |
  how\s+can\s+you\s+help(\s+me)?
)[\s?!.]*$""",
    re.IGNORECASE | re.VERBOSE,
)

# Pedidos de ejemplo meta (sin dataset concreto): no invocar plan + worker
# Nota: ``pued(es|as|a|e)`` cubre «puedes», «puedas», «puede», «pueda» (no usar ``pueda?s?``, que no casa «puedes»).
_CAPABILITIES_EXAMPLE_SMALLTALK = re.compile(
    r"""^[\s¿¡]*(
  d[aá]me\s+(un\s+)?ejemplo(\s+de\s+algo)?\s+que\s+pued(es|as|a|e)\s+hacer |
  d[aá]me\s+un\s+ejemplo\s+de\s+lo\s+que\s+pued(es|as|a|e)\s+hacer |
  (mu[eé]strame|ens[eé][ñn]ame)\s+(un\s+)?ejemplo(\s+de\s+algo\s+que\s+pued(es|as|a|e)\s+hacer)? |
  (mu[eé]strame|ens[eé][ñn]ame)\s+un\s+ejemplo |
  ejemplo\s+de\s+algo\s+que\s+pued(es|as|a|e)\s+hacer |
  un\s+ejemplo\s+de\s+lo\s+que\s+pued(es|as|a|e)\s+hacer |
  pued(es|as|a|e)\s+dar(me)?\s+un\s+ejemplo |
  alg[uú]n\s+ejemplo\s+de\s+lo\s+que\s+pued(es|as|a|e)\s+hacer |
  give\s+me\s+an?\s+example(\s+of\s+what\s+you\s+can\s+do)? |
  show\s+me\s+an?\s+example
)[\s?!.]*$""",
    re.IGNORECASE | re.VERBOSE,
)


def _is_capabilities_smalltalk(text: str) -> bool:
    """
    True si el usuario pide capacidades o un ejemplo genérico de uso, en una frase corta,
    sin datos concretos (evita plan LLM + invoke_worker).
    """
    raw = (text or "").strip()
    if not raw or raw.startswith("/"):
        return False
    if len(raw) > 120:
        return False
    # Pregunta meta + pedido concreto: mejor pasar por el planner
    if re.search(
        r"\b(con|sobre|analiz|datos|tabla|tablas|sql|ventas|csv|duckdb|query|métrica|metrica|grafico|gráfico)\b",
        raw,
        re.I,
    ):
        return False
    return bool(_CAPABILITIES_SMALLTALK.match(raw) or _CAPABILITIES_EXAMPLE_SMALLTALK.match(raw))


def _is_complex_task(row: dict) -> bool:
    """True si la tarea usó herramientas (tool use) o no es un saludo simple."""
    prefix = (row.get("query_prefix") or "").strip()
    if _is_simple_greeting(prefix):
        return False
    try:
        dur_ms = int(row.get("duration_ms") or 0)
    except (TypeError, ValueError):
        dur_ms = 0
    return dur_ms >= 1500 or len(prefix) > 20


def execute_history(db: Any, chat_id: Any, args: str) -> str:
    """/history [n]: historial de tareas complejas (tool use). Saludos simples (hola) se muestran como máximo uno."""
    tenant_s = str(chat_id).replace("'", "''")[:128]
    try:
        n = int((args or "5").strip())
        n = max(1, min(n, 20))
    except ValueError:
        n = 5
    _ensure_task_audit_log(db)
    try:
        r = db.query(
            f"""
            SELECT task_id, query_prefix, status, duration_ms, created_at, worker_id, plan_title
            FROM {_TASK_AUDIT_TABLE}
            WHERE tenant_id = '{tenant_s}'
            ORDER BY created_at DESC
            LIMIT 100
            """
        )
        rows = json.loads(r) if isinstance(r, str) else (r or [])
    except Exception as e:
        return f"Error al cargar historial: {e}."

    if not rows:
        return "📋 Sin tareas registradas."

    # Filtrar: tareas complejas con título de plan + como máximo 1 saludo simple
    complex_rows = []
    one_greeting = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        plan_title_raw = (row.get("plan_title") or "").strip()
        if _is_complex_task(row) and plan_title_raw:
            complex_rows.append(row)
        elif one_greeting is None and _is_simple_greeting(row.get("query_prefix") or ""):
            one_greeting = row
    filtered = complex_rows[:n]
    if one_greeting is not None and len(filtered) < n:
        filtered.append(one_greeting)

    if not filtered:
        return "📋 Sin tareas complejas."

    # Evitar duplicados: si hay varias filas con mismo worker/status/duración y
    # solo algunas tienen plan_title explícito, preferir las que sí lo tienen.
    deduped = []
    for idx, row in enumerate(filtered):
        if not isinstance(row, dict):
            continue
        raw_plan = (row.get("plan_title") or "").strip()
        if not raw_plan:
            wid = (row.get("worker_id") or "").strip()
            status = (row.get("status") or "UNKNOWN").upper()
            try:
                dur_ms = int(row.get("duration_ms") or 0)
            except (TypeError, ValueError):
                dur_ms = 0
            has_better = False
            for j, other in enumerate(filtered):
                if j == idx or not isinstance(other, dict):
                    continue
                other_plan = (other.get("plan_title") or "").strip()
                if not other_plan:
                    continue
                wid2 = (other.get("worker_id") or "").strip()
                status2 = (other.get("status") or "UNKNOWN").upper()
                try:
                    dur2 = int(other.get("duration_ms") or 0)
                except (TypeError, ValueError):
                    dur2 = 0
                if wid2 == wid and status2 == status and dur2 == dur_ms:
                    has_better = True
                    break
            if has_better:
                continue
        deduped.append(row)

    if not deduped:
        return "📋 Sin tareas complejas."

    lines = [f"📋 Últimas {len(deduped)}"]
    for i, row in enumerate(deduped, 1):
        if not isinstance(row, dict):
            continue
        prefix = (row.get("query_prefix") or "").strip()[:80]
        # Título del plan (guardado por el Manager): se muestra después del subagente
        plan_title = (row.get("plan_title") or "").strip()
        if not plan_title:
            # Fallback retrocompatible: derivar un pseudo-título desde query_prefix
            if prefix:
                words = prefix.split()
                plan_title = " ".join(words[:5])
            else:
                plan_title = "Interacción del Usuario"
        status = (row.get("status") or "UNKNOWN").upper()
        wid = (row.get("worker_id") or "").strip()
        try:
            dur_ms = int(row.get("duration_ms") or 0)
        except (TypeError, ValueError):
            dur_ms = 0
        dur_s = f"{dur_ms / 1000:.1f}s"
        # Formato: número. [subagente] Título del plan · ⏱️ duración
        worker_part = f"[{wid}] " if wid else ""
        title_part = plan_title if plan_title else ""
        lines.append(f"{i}. {worker_part}{title_part} · ⏱️ {dur_s}")

    success_rows = [r for r in filtered if isinstance(r, dict) and (r.get("status") or "").upper() == "SUCCESS"]
    def _dur(r):
        try:
            return int(r.get("duration_ms") or 0)
        except (TypeError, ValueError):
            return 0
    avg_ms = sum(_dur(r) for r in success_rows) / len(success_rows) if success_rows else 0
    try:
        r24 = db.query(
            f"""
            SELECT COUNT(*) as cnt FROM {_TASK_AUDIT_TABLE}
            WHERE tenant_id = '{tenant_s}' AND status = 'FAILED'
            AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            """
        )
        rows24 = json.loads(r24) if isinstance(r24, str) else (r24 or [])
        failed_24h = rows24[0].get("cnt", 0) if rows24 else 0
    except Exception:
        failed_24h = 0
    lines.append(f"— avg {avg_ms/1000:.1f}s · fallidas 24h: {failed_24h}")

    return "\n".join(lines)