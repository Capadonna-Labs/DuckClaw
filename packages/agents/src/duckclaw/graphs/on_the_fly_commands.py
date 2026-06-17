"""
On-the-Fly CLI: comandos de Telegram que mutan estado del grafo sin reiniciar.

Spec: specs/interfaz_de_comandos_dinamicos_On-the-Fly_CLI.md
"""

from __future__ import annotations

import os
from typing import Any
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
from duckclaw.commands.workers import (
    _DEFAULT_WORKER as _DEFAULT_WORKER,
    execute_roles as execute_roles,
    execute_skills_list as execute_skills_list,
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

from duckclaw.commands.fly_dispatch import (
    _dispatch_fly_command as _dispatch_fly_command,
    get_worker_id_for_chat as get_worker_id_for_chat,
    handle_command as handle_command,
    parse_command as parse_command,
)
from duckclaw.commands.fly_misc import (
    execute_approve_reject as execute_approve_reject,
    execute_help as execute_help,
    execute_lake_status as execute_lake_status,
    execute_tasks as execute_tasks,
)
from duckclaw.commands.fast_replies import (
    _is_capabilities_smalltalk as _is_capabilities_smalltalk,
)
from duckclaw.commands.fly_outbound import (
    pop_all_fly_outbound_charts as pop_all_fly_outbound_charts,
    pop_all_fly_outbound_charts_b64 as pop_all_fly_outbound_charts_b64,
    pop_fly_outbound_chart_b64 as pop_fly_outbound_chart_b64,
    register_fly_outbound_chart_b64 as register_fly_outbound_chart_b64,
)
from duckclaw.utils.telegram_markdown_v2 import (
    unescape_telegram_markdown_v2_layers as unescape_telegram_markdown_v2_layers,
)

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