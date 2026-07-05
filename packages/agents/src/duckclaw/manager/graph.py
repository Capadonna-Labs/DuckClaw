"""
Manager graph: thin facade — orchestration lives in ``manager_graph_builder`` and ``manager_*`` modules.

State: incoming, history, chat_id, reply, assigned_worker_id, planned_task, messages (opcional).
Flujo: router -> plan (formula tarea clara para el worker) -> invoke_worker (set_busy, invoca worker, set_idle, append_task_audit).
Spec: Plan manager orquestador de subagentes.

Las etiquetas de log ``{worker} {n}`` tras delegación son **subagent_slot_rank** (Redis), no IDs de réplica PM2;
ver ``duckclaw.graphs.subagent_run_id``.
"""

from __future__ import annotations

from duckclaw.graphs.subagent_run_id import acquire_subagent_slot, release_subagent_slot
from duckclaw.manager.fast_plans import _manager_visual_generation_intent, _try_capability_fast_plan
from duckclaw.manager.fast_replies import (
    _capabilities_fast_reply_text,
    _greeting_fast_reply_text,
    _manager_capabilities_fast_path_ok,
    _manager_greeting_fast_path_ok,
)
from duckclaw.manager.manager_delegation import (
    _load_orchestrator_planner_prompt,
    _resolve_orchestrator_delegate,
)
from duckclaw.manager.manager_entry_routes import (
    _duckdb_admin_write_intent,
    _is_entry_route_system_event,
    _is_goals_proactive_system_event,
    _worker_should_use_url_research_mcp_surface,
)
from duckclaw.manager.manager_graph_builder import build_manager_graph
from duckclaw.manager.manager_mercenary_policy import (
    _should_disable_mercenary_for_admin_ui,
    _should_disable_mercenary_for_browser_intent,
    _strip_mercenary_spec_for_browser_worker,
)
from duckclaw.manager.manager_plan_task import (
    _db_tool_pressure_task,
    _plan_task,
    _sanitize_manager_plan_title,
    _user_demands_tool_evidence_from_db,
)
from duckclaw.manager.manager_planner_llm import (
    _coerce_planner_payload,
    _extract_json_object,
    _llm_plan,
    _llm_plan_from_model,
    _truncate_plan_title_words,
)
from duckclaw.manager.manager_vault_config import (
    _agent_config_db_for_vault,
    _load_manager_task_policy,
)
from duckclaw.manager.manager_worker_cache import (
    _release_worker_db_handle,
    _vault_lock_key,
    _worker_graph_cache,
    clear_worker_graph_cache,
    trim_worker_graph_cache,
    worker_graph_cache_entry_count,
    worker_graph_cache_get,
    worker_graph_cache_stats,
)
from duckclaw.manager.routing import (
    _LONE_HTTP_URL_ONLY_LINE,
    _worker_id_alnum_slug,
    _worker_matches_id,
)

__all__ = [
    "acquire_subagent_slot",
    "build_manager_graph",
    "clear_worker_graph_cache",
    "release_subagent_slot",
    "trim_worker_graph_cache",
    "worker_graph_cache_entry_count",
    "worker_graph_cache_get",
    "worker_graph_cache_stats",
]
