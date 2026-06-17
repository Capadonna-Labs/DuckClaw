"""
On-the-Fly CLI: comandos de Telegram que mutan estado del grafo sin reiniciar.

Spec: specs/interfaz_de_comandos_dinamicos_On-the-Fly_CLI.md
"""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any, Optional, Tuple
from duckclaw.commands.chat_state import (
    _AGENT_CONFIG_TABLE as _AGENT_CONFIG_TABLE,
    _PREFIX as _PREFIX,
    _chat_key as _chat_key,
    _ensure_agent_config as _ensure_agent_config,
    _get_global_config as _get_global_config,
    _set_global_config as _set_global_config,
    _skip_runtime_ddl as _skip_runtime_ddl,
    execute_context_toggle as execute_context_toggle,
    execute_forget as execute_forget,
    get_chat_state as get_chat_state,
    set_chat_state as set_chat_state,
)
from duckclaw.commands.audit import (
    execute_audit as execute_audit,
    save_last_audit as save_last_audit,
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
from duckclaw.commands.comfyui import (
    _COMFYUI_PROVIDER_KEY as _COMFYUI_PROVIDER_KEY,
    execute_comfyui_provider as execute_comfyui_provider,
)
from duckclaw.commands.meditate import (
    MEDITATE_DELTA_MAX_SECONDS as MEDITATE_DELTA_MAX_SECONDS,
    MEDITATE_DELTA_MIN_SECONDS as MEDITATE_DELTA_MIN_SECONDS,
    _MEDITATE_DELTA_SECONDS_KEY as _MEDITATE_DELTA_SECONDS_KEY,
    _MEDITATE_LAST_FIRE_KEY as _MEDITATE_LAST_FIRE_KEY,
    _MEDITATE_TENANT_KEY as _MEDITATE_TENANT_KEY,
    _MEDITATE_WORKER_KEY as _MEDITATE_WORKER_KEY,
    _format_meditate_cycle_summary as _format_meditate_cycle_summary,
    _publish_meditate_tick_heartbeat as _publish_meditate_tick_heartbeat,
    _resolve_meditate_vault_user_id as _resolve_meditate_vault_user_id,
    apply_meditate_schedule as apply_meditate_schedule,
    chat_id_from_meditate_delta_config_key as chat_id_from_meditate_delta_config_key,
    clear_meditate_schedule as clear_meditate_schedule,
    configure_meditate_tick_heartbeat_publisher as _configure_meditate_tick_heartbeat_publisher,
    execute_meditate as execute_meditate,
    get_meditate_schedule_status as get_meditate_schedule_status,
    invoke_meditate_cycle_for_chat as invoke_meditate_cycle_for_chat,
    parse_meditate_delta_arg as parse_meditate_delta_arg,
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
from duckclaw.commands.history import (
    _TASK_AUDIT_TABLE as _TASK_AUDIT_TABLE,
    _ensure_task_audit_log as _ensure_task_audit_log,
    _infer_user_id_for_audit_queue as _infer_user_id_for_audit_queue,
    _is_complex_task as _is_complex_task,
    _is_simple_greeting as _is_simple_greeting,
    append_task_audit as append_task_audit,
    execute_history as execute_history,
    get_history_limit_for_chat as get_history_limit_for_chat,
)
from duckclaw.commands.health import (
    configure_heartbeat_adapter as _configure_heartbeat_adapter,
    execute_health as execute_health,
    execute_heartbeat as execute_heartbeat,
)
from duckclaw.commands.hitl import (
    execute_code_approve as execute_code_approve,
    execute_code_reject as execute_code_reject,
    execute_resolve_uncertainty as execute_resolve_uncertainty,
    execute_uncertainty_status as execute_uncertainty_status,
)
from duckclaw.commands.model_setup import (
    _DEFAULT_BASE_URL_BY_PROVIDER as _DEFAULT_BASE_URL_BY_PROVIDER,
    _DEFAULT_MODEL_BY_PROVIDER as _DEFAULT_MODEL_BY_PROVIDER,
    _PROVIDERS as _PROVIDERS,
    _debug_log_model_config as _debug_log_model_config,
    _effective_llm_triplet_for_chat_ui as _effective_llm_triplet_for_chat_ui,
    _execute_setup as _execute_setup,
    _gemini_models_list_from_api as _gemini_models_list_from_api,
    _parse_pipe_kv_args as _parse_pipe_kv_args,
    chat_has_llm_chat_state_override as chat_has_llm_chat_state_override,
    configure_prompt_system_fallback_provider as _configure_prompt_system_fallback_provider,
    configure_prompt_template_ids_provider as _configure_prompt_template_ids_provider,
    execute_model as execute_model,
    execute_models as execute_models,
    execute_prompt as execute_prompt,
    execute_setup as execute_setup,
    get_effective_system_prompt as get_effective_system_prompt,
    resolve_llm_triplet_for_chat_invocation as resolve_llm_triplet_for_chat_invocation,
)
from duckclaw.commands.runtime_toggles import (
    configure_sandbox_session_cleanup as configure_sandbox_session_cleanup,
    execute_internet_toggle as execute_internet_toggle,
    execute_sandbox_toggle as execute_sandbox_toggle,
)
from duckclaw.commands.sensors import (
    _browser_sandbox_sensor_lines as _browser_sandbox_sensor_lines,
    _lake_ssh_status_lines as _lake_ssh_status_lines,
    _sensor_line_bullet as _sensor_line_bullet,
    _ssh_reach_icon as _ssh_reach_icon,
    configure_browser_sandbox_sensor_lines_provider as _configure_browser_sandbox_sensor_lines_provider,
    execute_sensors as execute_sensors,
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


class _GraphHeartbeatAdapter:
    def heartbeat_redis_configured(self) -> bool:
        from duckclaw.graphs.chat_heartbeat import heartbeat_redis_configured

        return heartbeat_redis_configured()

    def heartbeat_outbound_configured(self) -> bool:
        from duckclaw.graphs.chat_heartbeat import heartbeat_outbound_configured

        return heartbeat_outbound_configured()

    def is_admin_ui_chat_session(self, chat_id: str) -> bool:
        from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

        return is_admin_ui_chat_session(chat_id)

    def is_chat_heartbeat_enabled(self, db: Any, tenant_id: str, chat_id: str) -> bool:
        from duckclaw.graphs.chat_heartbeat import is_chat_heartbeat_enabled

        return is_chat_heartbeat_enabled(tenant_id, chat_id, db=db)

    def set_chat_heartbeat_enabled(
        self, db: Any, tenant_id: str, chat_id: str, on: bool
    ) -> tuple[bool, str]:
        from duckclaw.graphs.chat_heartbeat import set_chat_heartbeat_enabled

        return set_chat_heartbeat_enabled(tenant_id, chat_id, on, db=db)


_configure_heartbeat_adapter(_GraphHeartbeatAdapter())


class _GraphMeditateTickHeartbeatPublisher:
    def publish_meditate_tick(
        self,
        chat_id: Any,
        *,
        tenant_id: str,
        worker_id: str,
        summary: str,
    ) -> None:
        from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session, publish_admin_chat_heartbeat

        cid = str(chat_id or "").strip()
        if not cid or not is_admin_ui_chat_session(cid):
            return
        publish_admin_chat_heartbeat(
            cid,
            f"[meditate] {summary}",
            kind="meditate_tick",
            worker_id=worker_id,
            artifact_tenant_id=tenant_id,
        )


_configure_meditate_tick_heartbeat_publisher(_GraphMeditateTickHeartbeatPublisher())
try:
    from duckclaw.graphs.chat_heartbeat import configure_heartbeat_runtime_db_provider

    configure_heartbeat_runtime_db_provider(get_db)
except Exception:
    pass
try:
    from duckclaw.workers.provider_input_budget import configure_provider_budget_runtime_db_provider

    configure_provider_budget_runtime_db_provider(get_db)
except Exception:
    pass


def _sandbox_session_cleanup(chat_id: str) -> None:
    """Adapter graph-local for runtime toggle sandbox cleanup."""
    from duckclaw.graphs.sandbox import cleanup_sandbox_session_for_chat

    cleanup_sandbox_session_for_chat(chat_id)


configure_sandbox_session_cleanup(_sandbox_session_cleanup)


def _prompt_template_ids_provider() -> list[str]:
    """Adapter graph-local for legacy /prompt worker validation."""
    from duckclaw.workers.factory import list_workers

    return list_workers()


def _prompt_system_fallback_provider(worker_id: str) -> str:
    """Load only the default worker prompt fallback from the filesystem layout."""
    wid = (worker_id or "").strip()
    if wid != "default":
        return ""
    try:
        from duckclaw.workers.manifest import load_manifest
        from duckclaw.workers.loader import load_system_prompt

        spec = load_manifest(wid)
        return (load_system_prompt(spec) or "").strip()
    except Exception:
        return ""


_configure_prompt_template_ids_provider(_prompt_template_ids_provider)
_configure_prompt_system_fallback_provider(_prompt_system_fallback_provider)
_configure_goals_llm_triplet_resolver(_effective_llm_triplet_for_chat_ui)


def _browser_sandbox_sensor_lines_provider() -> list[str]:
    """Adapter graph-local for browser sandbox diagnostics used by /sensors."""
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


_configure_browser_sandbox_sensor_lines_provider(_browser_sandbox_sensor_lines_provider)

_configure_goals_vault_user_id_resolver(_resolve_meditate_vault_user_id)

# Cola FIFO de PNG base64 por chat: api-gateway hace pop_all y sendPhoto en orden.
_FLY_OUTBOUND_CHART_B64: dict[str, list[str]] = {}


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


def execute_lake_status() -> str:
    """/lake [status]: variables de lake y prueba SSH corta (BatchMode, ConnectTimeout=5)."""
    try:
        lines = _lake_ssh_status_lines(compact=False)
    except Exception as e:
        return f"Lake: no se pudo leer conectividad: {e}"
    return "\n".join(lines)


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
        return execute_forget(db, chat_id, tenant_id=tenant_id)
    if name == "context":
        return execute_context_toggle(db, chat_id, args, tenant_id=tenant_id)
    if name == "comfyui":
        return execute_comfyui_provider(db, chat_id, args, tenant_id=tenant_id)
    if name in ("sandbox", "sandox"):
        return execute_sandbox_toggle(db, chat_id, args, tenant_id=tenant_id)
    if name in ("internet", "red", "network"):
        return execute_internet_toggle(
            db,
            chat_id,
            args,
            worker_id=entry_worker_id or "",
            tenant_id=tenant_id,
        )
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


def get_worker_id_for_chat(db: Any, chat_id: Any) -> str:
    """Devuelve el worker_id asignado a este chat. Por defecto: manager (orquesta y delega a templates)."""
    return get_chat_state(db, chat_id, "worker_id") or _DEFAULT_WORKER


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