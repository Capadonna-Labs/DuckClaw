"""
WorkerFactory: build a LangGraph instance from a worker template.

Thin facade — graph assembly lives in ``factory_graph_builder``; helpers in
``factory_*`` sibling modules. Public imports remain stable via re-exports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from duckclaw.egress.tool_response_repair import (
    clock_only_lone_url_no_repair as _clock_only_lone_url_no_repair,
    deterministic_tool_response_summary as _deterministic_tool_response_summary,
    latest_tool_json_since as _latest_tool_json_since,
    parse_get_current_time_json as _parse_get_current_time_json,
    post_tools_synthesis_needed as _post_tools_synthesis_needed,
    repair_tool_response_egress_reply as _repair_tool_response_egress_reply,
    reply_is_get_current_time_json_only as _reply_is_get_current_time_json_only,
    reply_is_tool_json_echo as _reply_is_tool_json_echo,
    tool_response_needs_egress_repair as _tool_response_needs_egress_repair,
)
from duckclaw.workers.context_monitor import (
    build_context_monitor_node as _build_context_monitor_node,
    build_summary_llm as _build_summary_llm,
    compose_context_summary_prompt as _compose_context_summary_prompt,
    llm_fold_conversation_summary as _llm_fold_conversation_summary,
    serialize_messages_for_summary as _serialize_messages_for_summary,
)
from duckclaw.workers.db_intent_policy import (
    TABLE_CONTENT_PHRASE as _TABLE_CONTENT_PHRASE,
    explicit_duckdb_schema_request,
    explicit_duckdb_storage_request,
    incoming_is_manager_planned_guardrail_task,
    incoming_is_schema_query_heuristic,
    incoming_is_table_content_query as _incoming_is_table_content_query,
    is_no_task as _is_no_task,
)
from duckclaw.workers.db_runtime import (
    RUN_SANDBOX_TOOL_LLM_MAX_CHARS as _RUN_SANDBOX_TOOL_LLM_MAX_CHARS,
    apply_forge_attaches as _apply_forge_attaches,
    bootstrap_shared_main_schema as _bootstrap_shared_main_schema,
    get_db_path as _get_db_path,
    infer_user_id_for_writer as _infer_user_id_for_writer,
    resolve_shared_db_path as _resolve_shared_db_path,
    same_duckdb_file as _same_duckdb_file,
    truncate_read_sql_result_for_llm as _truncate_read_sql_result_for_llm,
)
from duckclaw.workers.discovery import list_workers
from duckclaw.workers.factory_agent_node_helpers import (
    _agent_node_llm_failure_user_message,
    _duckclaw_env_truthy,
    _identity_fields,
    _last_human_message_index,
    _parse_comfyui_edit_inbound,
    _raise_if_chat_cancelled_from_state,
    _spec_logical_worker_id,
    _visual_asset_calls_since_last_human,
    _worker_log_label,
)
from duckclaw.workers.factory_graph_builder import build_worker_graph
from duckclaw.workers.factory_reddit_helpers import (
    _extract_first_reddit_url,
    _fetch_reddit_post_via_public_json,
    _latest_human_index_with_reddit_share_url,
    _most_recent_reddit_url_in_human_messages,
    _patch_reddit_get_post_args_from_canonical_url,
    _reddit_comments_url_has_share_tracking,
    _reddit_tools_paused,
    _reddit_trust_share_tracking_redirect,
    _resolve_reddit_share_url_to_comments_url,
    _subreddit_and_post_id_from_reddit_comments_url,
    reddit_share_search_query_for_attempt,
    reddit_share_shortlink_fallback_query,
)
from duckclaw.workers.factory_sandbox_notify import (
    _heartbeat_elapsed_sec,
    _novnc_pre_dm_always_enabled,
    _sandbox_heartbeat_allowed,
    _schedule_run_browser_novnc_tool_heartbeat,
    _send_novnc_pre_dm_fallback,
    _send_sandbox_heartbeat_telegram,
)
from duckclaw.workers.factory_tool_builder import (
    _build_worker_tools,
    _ensure_worker_duckdb_extensions,
)
from duckclaw.workers.provider_input_budget import (
    apply_groq_message_budget as _apply_groq_message_budget,
    apply_mlx_message_budget as _apply_mlx_message_budget,
    apply_provider_input_budget as _apply_provider_input_budget,
    configure_provider_budget_runtime_db_provider as _configure_provider_budget_runtime_db_provider,
    estimate_tokens_from_messages as _estimate_tokens_from_messages,
    groq_max_estimated_input_tokens as _groq_max_estimated_input_tokens,
    groq_tool_message_max_chars as _groq_tool_message_max_chars,
    mlx_max_estimated_input_tokens as _mlx_max_estimated_input_tokens,
    mlx_tool_message_max_chars as _mlx_tool_message_max_chars,
    normalized_context_pruning as _normalized_context_pruning,
    split_for_pruning as _split_for_pruning,
    trim_messages_to_estimated_cap as _trim_messages_to_estimated_cap,
)
from duckclaw.workers.runtime_policy_helpers import (
    worker_has_runtime_capability as _worker_has_runtime_capability,
    worker_runtime_capability_flag as _worker_runtime_capability_flag,
    worker_runtime_capability_policy as _worker_runtime_capability_policy,
    worker_runtime_policy as _worker_runtime_policy,
    worker_use_heuristic_first_tool as _worker_use_heuristic_first_tool,
)
from duckclaw.workers.skill_tool_registry import (
    read_visual_artifact_image_as_b64 as _read_visual_artifact_image_as_b64,
    register_post_llm_skill_tools as _register_post_llm_skill_tools,
    register_pre_llm_skill_tools as _register_pre_llm_skill_tools,
)
from duckclaw.workers.tool_binding import (
    filter_tools_for_sandbox,
    groq_tools_without_reddit_for_bind as _groq_tools_without_reddit_for_bind,
    tool_called_since as _tool_called_since,
    tool_choice_function as _tool_choice_function,
)
from duckclaw.workers.tool_invocation_policy import (
    decide_current_time_tool_invocation as _decide_current_time_tool_invocation,
    decide_db_first_tool_invocation as _decide_db_first_tool_invocation,
)
from duckclaw.workers.tool_output_truncation import (
    compact_run_sandbox_tool_content_for_llm as _compact_run_sandbox_tool_content_for_llm,
    truncate_tool_messages_for_llm as _truncate_tool_messages,
)
from duckclaw.workers.visual_evidence_policy import (
    visual_evidence_max_retries as _visual_evidence_max_retries,
)


class WorkerFactory:
    """Factory for Virtual Workers (template-based LangGraph agents)."""

    def __init__(self, templates_root: Optional[Path] = None):
        self.templates_root = templates_root

    def create(
        self,
        worker_id: str,
        db_path: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        instance_name: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        shared_db_path: Optional[str] = None,
    ) -> Any:
        """
        Build and return a compiled LangGraph for the worker.
        Shim: delega a build_worker_graph (compatible con AgentAssembler).
        """
        return build_worker_graph(
            worker_id,
            db_path,
            None,
            templates_root=self.templates_root,
            instance_name=instance_name,
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            shared_db_path=shared_db_path,
            tool_surface="full",
        )


__all__ = [
    "WorkerFactory",
    "build_worker_graph",
    "explicit_duckdb_schema_request",
    "explicit_duckdb_storage_request",
    "filter_tools_for_sandbox",
    "incoming_is_schema_query_heuristic",
    "list_workers",
    "reddit_share_search_query_for_attempt",
    "reddit_share_shortlink_fallback_query",
]
