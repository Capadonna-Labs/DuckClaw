#!/usr/bin/env python3
"""Split factory_graph_builder.py into modular factory_graph_* modules."""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "packages/agents/src/duckclaw/workers"
SRC = (ROOT / "factory_graph_builder.py").read_text(encoding="utf-8")
SRC_LINES = SRC.splitlines(keepends=True)


def extract(start: int, end: int) -> str:
    chunk = SRC_LINES[start - 1 : end]
    out: list[str] = []
    for ln in chunk:
        if ln.startswith("    "):
            out.append(ln[4:])
        elif ln.strip() == "":
            out.append("\n")
        else:
            out.append(ln)
    return "".join(out)


def write(name: str, content: str) -> int:
    path = ROOT / name
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    n = len(content.splitlines())
    print(f"  {name}: {n} lines")
    return n


PREPARE_UNPACK = dedent(
    """
    effective_prompt = ctx.effective_prompt
    _context_prompt_base = ctx.context_prompt_base
    provider = ctx.provider
    _cp = ctx.context_pruning
"""
)

SANDBOX_UNPACK = dedent(
    """
    db = ctx.db
"""
)

AGENT_BIND_BODY = extract(476, 582)

REDDIT_HELPERS_BODY = extract(584, 702)

AGENT_INVOKE_BODY = extract(705, 1470)

TOOLS_BODY = extract(1473, 1821)

SET_REPLY_BODY = extract(1824, 2120)

ROUTING_SHOULD_CONTINUE = extract(2123, 2125)
ROUTING_FACT_CHECK = extract(2136, 2137)
ROUTING_SELF_CORRECTION = extract(2140, 2141)
ROUTING_HANDOFF = extract(2144, 2145)
ROUTING_AFTER_FACT = extract(2148, 2148)
ROUTING_AFTER_SET_REPLY = extract(2151, 2151)
ROUTING_HOMEOSTASIS = extract(2154, 2156)

SETUP_BODY = extract(229, 369) + "\n" + extract(420, 425) + "\n" + extract(445, 457)

AGENT_NO_LLM = extract(461, 466)

PREPARE_BODY = extract(372, 418)

SANDBOX_CHECKER_BODY = extract(428, 443)

ASSEMBLY_GRAPH = extract(2158, 2207)


def main() -> None:
    print("Generating factory_graph_* modules from monolith...")

    write(
        "factory_graph_context.py",
        dedent(
            '''
            """Shared context for worker LangGraph node factories."""

            from __future__ import annotations

            from dataclasses import dataclass, field
            from typing import Any, Literal, Optional


            @dataclass
            class WorkerGraphContext:
                """Graph-build locals formerly closed over by nested node functions."""

                worker_id: str = ""
                db: Any = None
                spec: Any = None
                path: str = ""
                shared_resolved: str = ""
                provider: str = ""
                model: str = ""
                base_url: str = ""
                llm: Any = None
                llm_fallback: Any | None = None
                tool_surface: Literal["full", "context_synthesis", "visual_generation", "url_research"] = "full"
                tenant_id: str = "default"
                instance_name: Optional[str] = None
                is_market_analysis_worker: bool = False
                system_prompt: str = ""
                effective_prompt: str = ""
                context_prompt_base: Optional[str] = None
                context_pruning: dict[str, Any] = field(default_factory=dict)
                use_context_monitor: bool = False
                schema_digest: str = ""
                logical_worker_id: str = ""
                prompt_policies: Any = None
                tools: list[Any] = field(default_factory=list)
                tools_by_name: dict[str, Any] = field(default_factory=dict)
                tools_sandbox_off: list[Any] = field(default_factory=list)
                tools_by_name_sandbox_off: dict[str, Any] = field(default_factory=dict)
                groq_bind: bool = False
                tools_for_llm_bind: list[Any] = field(default_factory=list)
                tools_sandbox_off_bind: list[Any] = field(default_factory=list)
                llm_summary: Any = None
                context_monitor_node: Any = None
                sandbox_enabled_for_state: Any = None
                agent_bind: dict[str, Any] = field(default_factory=dict)
                context_guard_enabled: bool = False
                context_guard_max_retries: int = 2
            '''
        ),
    )

    write(
        "factory_graph_setup.py",
        dedent(
            f'''
            """DB/tools/LLM initialization for worker LangGraph assembly."""

            from __future__ import annotations

            import logging
            import os
            from pathlib import Path
            from typing import Any, Literal, Optional

            from duckclaw.prompt_policies import PromptPolicyResolver
            from duckclaw.workers.context_monitor import (
                build_context_monitor_node as _build_context_monitor_node,
                build_summary_llm as _build_summary_llm,
            )
            from duckclaw.workers.db_runtime import (
                apply_forge_attaches as _apply_forge_attaches,
                get_db_path as _get_db_path,
                resolve_shared_db_path as _resolve_shared_db_path,
                same_duckdb_file as _same_duckdb_file,
            )
            from duckclaw.workers.factory_agent_node_helpers import (
                _TASK_AWARENESS_PROMPT,
                _identity_fields,
            )
            from duckclaw.workers.factory_graph_agent_bind import build_agent_llm_bind
            from duckclaw.workers.factory_graph_context import WorkerGraphContext
            from duckclaw.workers.factory_tool_builder import _build_worker_tools
            from duckclaw.workers.identity import load_worker_runtime_policy
            from duckclaw.workers.loader import append_domain_closure_block, load_system_prompt
            from duckclaw.workers.manifest import load_manifest
            from duckclaw.workers.provider_input_budget import (
                configure_provider_budget_runtime_db_provider as _configure_provider_budget_runtime_db_provider,
                normalized_context_pruning as _normalized_context_pruning,
            )
            from duckclaw.workers.runtime_policy_helpers import (
                worker_has_runtime_capability as _worker_has_runtime_capability,
            )
            from duckclaw.workers.skill_tool_registry import (
                register_post_llm_skill_tools as _register_post_llm_skill_tools,
                register_pre_llm_skill_tools as _register_pre_llm_skill_tools,
            )
            from duckclaw.workers.tool_binding import (
                filter_tools_for_sandbox,
                groq_tools_without_reddit_for_bind as _groq_tools_without_reddit_for_bind,
            )

            _log = logging.getLogger(__name__)


            def initialize_worker_graph_context(
                worker_id: str,
                db_path: Optional[str],
                llm: Optional[Any],
                *,
                templates_root: Optional[Path] = None,
                instance_name: Optional[str] = None,
                llm_provider: Optional[str] = None,
                llm_model: Optional[str] = None,
                llm_base_url: Optional[str] = None,
                shared_db_path: Optional[str] = None,
                reuse_db: Any | None = None,
                tool_surface: Literal["full", "context_synthesis", "visual_generation", "url_research"] = "full",
                incoming_hint: str | None = None,
                open_vault_read_only: bool = False,
                db: Any | None = None,
                tenant_id: str = "default",
            ) -> WorkerGraphContext:
                ctx = WorkerGraphContext(
                    worker_id=worker_id,
                    tool_surface=tool_surface,
                    tenant_id=tenant_id,
                    instance_name=instance_name,
                    llm=llm,
                )
                spec = load_manifest(worker_id, templates_root, db=db, tenant_id=tenant_id)
                ctx.spec = spec
                if db is not None:
                    try:
                        spec.runtime_policy = load_worker_runtime_policy(
                            db,
                            getattr(spec, "logical_worker_id", None) or worker_id,
                            tenant_id=tenant_id,
                        )
                    except Exception as exc:
                        _log.debug("worker runtime policy unavailable for %s: %s", worker_id, exc)
                ctx.is_market_analysis_worker = _worker_has_runtime_capability(spec, "market_analysis")
                path = _get_db_path(worker_id, instance_name, db_path)
                ctx.path = path
                shared_resolved = _resolve_shared_db_path(spec, shared_db_path)
                ctx.shared_resolved = shared_resolved

                from duckclaw import DuckClaw

                reuse_path = ""
                if reuse_db is not None:
                    reuse_path = str(getattr(reuse_db, "_path", "") or "").strip()
                reuse_read_only = bool(getattr(reuse_db, "_read_only", False)) if reuse_db is not None else False
                same_as_reuse = bool(reuse_db is not None and reuse_path and _same_duckdb_file(reuse_path, path))
                effective_vault_ro = bool(spec.read_only) or bool(open_vault_read_only)
                if same_as_reuse and not (shared_resolved or "").strip() and not open_vault_read_only:
                    db = reuse_db
                    _log.debug(
                        "build_worker_graph: reuse DuckClaw (same file) path=%s ro=%s",
                        path, reuse_read_only,
                    )
                else:
                    from typing import Literal as _Literal

                    _engine: _Literal["auto", "python"] = (
                        "python"
                        if not effective_vault_ro and (path or "").strip() not in ("", ":memory:")
                        else "auto"
                    )
                    db = DuckClaw(path, read_only=effective_vault_ro, engine=_engine)
                ctx.db = db
{SETUP_BODY}
                context_guard_config = getattr(spec, "context_guard_config", None) or {{}}
                ctx.context_guard_enabled = (
                    bool(context_guard_config.get("enabled", False))
                    and "catalog_retriever" in (spec.skills_list or [])
                )
                ctx.context_guard_max_retries = int(context_guard_config.get("max_retries", 2))

                ctx.prompt_policies = prompt_policies
                ctx.system_prompt = system_prompt
                ctx.tools = tools
                ctx.tools_by_name = tools_by_name
                ctx.provider = provider
                ctx.model = model
                ctx.base_url = base_url
                ctx.llm = llm
                ctx.llm_fallback = llm_fallback
                ctx.llm_summary = llm_summary
                ctx.effective_prompt = effective_prompt
                ctx.logical_worker_id = _lid
                ctx.context_pruning = _cp
                ctx.use_context_monitor = use_cm
                ctx.context_prompt_base = _context_prompt_base
                ctx.context_monitor_node = context_monitor_node
                ctx.tools_sandbox_off = tools_sandbox_off
                ctx.tools_by_name_sandbox_off = tools_by_name_sandbox_off
                ctx.groq_bind = _groq_bind
                ctx.tools_for_llm_bind = _tools_for_llm_bind
                ctx.tools_sandbox_off_bind = _tools_sandbox_off_bind

                if llm is not None:
                    build_agent_llm_bind(ctx)
                return ctx
            '''
        ),
    )

    write(
        "factory_graph_nodes_prepare.py",
        dedent(
            f'''
            """prepare_node and sandbox session checker."""

            from __future__ import annotations

            from typing import Any, Optional

            try:
                from langchain_core.runnables import RunnableConfig
            except ImportError:
                RunnableConfig = Any  # type: ignore[misc, assignment]

            from duckclaw.workers.context_monitor import compose_context_summary_prompt as _compose_context_summary_prompt
            from duckclaw.workers.db_intent_policy import is_no_task as _is_no_task
            from duckclaw.workers.factory_agent_node_helpers import _identity_fields
            from duckclaw.workers.factory_graph_context import WorkerGraphContext
            from duckclaw.workers.provider_input_budget import apply_provider_input_budget as _apply_provider_input_budget
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


            def make_prepare_node(ctx: WorkerGraphContext):
                {PREPARE_UNPACK}
                def prepare_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
            {PREPARE_BODY}
                return prepare_node


            def make_sandbox_enabled_for_state(ctx: WorkerGraphContext):
                {SANDBOX_UNPACK}
                def _sandbox_enabled_for_state(state: dict) -> bool:
            {SANDBOX_CHECKER_BODY}
                return _sandbox_enabled_for_state
            '''
        ),
    )

    write(
        "factory_graph_agent_bind.py",
        dedent(
            f'''
            """LLM tool-binding cache for agent node."""

            from __future__ import annotations

            import logging

            from duckclaw.workers.factory_graph_context import WorkerGraphContext
            from duckclaw.workers.tool_binding import (
                groq_tools_without_reddit_for_bind as _groq_tools_without_reddit_for_bind,
                tool_choice_function as _tool_choice_function,
            )

            _log = logging.getLogger(__name__)


            def build_agent_llm_bind(ctx: WorkerGraphContext) -> None:
                llm = ctx.llm
                tools = ctx.tools
                tools_by_name = ctx.tools_by_name
                tools = ctx.tools
                tools_by_name = ctx.tools_by_name
                tools_sandbox_off = ctx.tools_sandbox_off
                tools_by_name_sandbox_off = ctx.tools_by_name_sandbox_off
                _tools_for_llm_bind = ctx.tools_for_llm_bind
                _tools_sandbox_off_bind = ctx.tools_sandbox_off_bind
                if llm is None:
                    return
                from duckclaw.integrations.llm_providers import bind_tools_with_parallel_default as _bind_tools
            {AGENT_BIND_BODY}
                ctx.agent_bind = {{
                    "llm_with_tools_on": llm_with_tools_on,
                    "llm_with_tools_off": llm_with_tools_off,
                    "llm_force_schema_on": llm_force_schema_on,
                    "llm_force_schema_off": llm_force_schema_off,
                    "llm_force_read_sql_on": llm_force_read_sql_on,
                    "llm_force_read_sql_off": llm_force_read_sql_off,
                    "llm_force_admin_sql_on": llm_force_admin_sql_on,
                    "llm_force_admin_sql_off": llm_force_admin_sql_off,
                    "llm_force_run_sandbox_on": llm_force_run_sandbox_on,
                    "llm_force_run_sandbox_off": llm_force_run_sandbox_off,
                    "llm_force_tavily_on": llm_force_tavily_on,
                    "llm_force_tavily_off": llm_force_tavily_off,
                    "llm_force_generate_visual_on": llm_force_generate_visual_on,
                    "llm_force_generate_visual_off": llm_force_generate_visual_off,
                    "llm_force_fetch_market_on": llm_force_fetch_market_on,
                    "llm_force_fetch_market_off": llm_force_fetch_market_off,
                    "llm_force_reddit_post_on": llm_force_reddit_post_on,
                    "llm_force_reddit_post_off": llm_force_reddit_post_off,
                    "llm_force_reddit_search_on": llm_force_reddit_search_on,
                    "llm_force_reddit_search_off": llm_force_reddit_search_off,
                    "llm_force_reddit_fallback_on": llm_force_reddit_fallback_on,
                    "llm_force_reddit_fallback_off": llm_force_reddit_fallback_off,
                    "has_read_sql": has_read_sql,
                    "has_tavily": has_tavily,
                    "has_generate_visual": has_generate_visual,
                    "has_reddit_tools": has_reddit_tools,
                    "has_run_sandbox": has_run_sandbox,
                }}
            '''
        ),
    )

    write(
        "factory_graph_agent_reddit_helpers.py",
        dedent(
            f'''
            """Reddit helpers extracted from agent node."""

            from __future__ import annotations

            import json
            import re
            from typing import Any, Optional

            from duckclaw.workers.db_intent_policy import incoming_is_schema_query_heuristic
            from duckclaw.workers.factory_reddit_helpers import (
                _extract_first_reddit_url,
                reddit_share_search_query_for_attempt,
            )
            from langchain_core.messages import ToolMessage

            {REDDIT_HELPERS_BODY}
            '''
        ),
    )

    agent_unpack = dedent(
        """
    worker_id = ctx.worker_id
    db = ctx.db
    spec = ctx.spec
    path = ctx.path
    shared_resolved = ctx.shared_resolved
    provider = ctx.provider
    llm = ctx.llm
    tool_surface = ctx.tool_surface
    is_market_analysis_worker = ctx.is_market_analysis_worker
    tools = ctx.tools
    tools_by_name = ctx.tools_by_name
    tools_sandbox_off = ctx.tools_sandbox_off
    tools_by_name_sandbox_off = ctx.tools_by_name_sandbox_off
    prompt_policies = ctx.prompt_policies
    _lid = ctx.logical_worker_id
    use_cm = ctx.use_context_monitor
    _tools_for_llm_bind = ctx.tools_for_llm_bind
    _tools_sandbox_off_bind = ctx.tools_sandbox_off_bind
    _sandbox_enabled_for_state = ctx.sandbox_enabled_for_state
    b = ctx.agent_bind
    llm_with_tools_on = b.get("llm_with_tools_on")
    llm_with_tools_off = b.get("llm_with_tools_off")
    llm_force_schema_on = b.get("llm_force_schema_on")
    llm_force_schema_off = b.get("llm_force_schema_off")
    llm_force_read_sql_on = b.get("llm_force_read_sql_on")
    llm_force_read_sql_off = b.get("llm_force_read_sql_off")
    llm_force_admin_sql_on = b.get("llm_force_admin_sql_on")
    llm_force_admin_sql_off = b.get("llm_force_admin_sql_off")
    llm_force_run_sandbox_on = b.get("llm_force_run_sandbox_on")
    llm_force_run_sandbox_off = b.get("llm_force_run_sandbox_off")
    llm_force_tavily_on = b.get("llm_force_tavily_on")
    llm_force_tavily_off = b.get("llm_force_tavily_off")
    llm_force_generate_visual_on = b.get("llm_force_generate_visual_on")
    llm_force_generate_visual_off = b.get("llm_force_generate_visual_off")
    llm_force_fetch_market_on = b.get("llm_force_fetch_market_on")
    llm_force_fetch_market_off = b.get("llm_force_fetch_market_off")
    llm_force_reddit_post_on = b.get("llm_force_reddit_post_on")
    llm_force_reddit_post_off = b.get("llm_force_reddit_post_off")
    llm_force_reddit_search_on = b.get("llm_force_reddit_search_on")
    llm_force_reddit_search_off = b.get("llm_force_reddit_search_off")
    llm_force_reddit_fallback_on = b.get("llm_force_reddit_fallback_on")
    llm_force_reddit_fallback_off = b.get("llm_force_reddit_fallback_off")
    has_read_sql = b.get("has_read_sql", False)
    has_tavily = b.get("has_tavily", False)
    has_generate_visual = b.get("has_generate_visual", False)
    has_reddit_tools = b.get("has_reddit_tools", False)
    has_run_sandbox = b.get("has_run_sandbox", False)
    from duckclaw.integrations.llm_providers import bind_tools_with_parallel_default as _bind_tools
    from duckclaw.workers.factory_graph_agent_reddit_helpers import (
        count_tool_messages_named as _count_tool_messages_named,
        first_reddit_url_in_text as _first_reddit_url_in_text,
        incoming_has_reddit_share_path as _incoming_has_reddit_share_path,
        incoming_has_reddit_url as _incoming_has_reddit_url,
        incoming_looks_like_reddit_post_url as _incoming_looks_like_reddit_post_url,
        is_latest_game_query as _is_latest_game_query,
        is_schema_query as _is_schema_query,
        patch_ai_reddit_share_tool_calls as _patch_ai_reddit_share_tool_calls,
        reddit_share_slug_from_incoming as _reddit_share_slug_from_incoming,
        reddit_tool_message_no_data as _reddit_tool_message_no_data,
    )
"""
    )

    write(
        "factory_graph_nodes_agent_invoke.py",
        dedent(
            f'''
            """Agent node LLM invocation body."""

            from __future__ import annotations

            import json
            import logging
            import time
            from typing import Any, Optional

            try:
                from langchain_core.runnables import RunnableConfig
            except ImportError:
                RunnableConfig = Any  # type: ignore[misc, assignment]

            from duckclaw.egress.tool_response_repair import (
                clock_only_lone_url_no_repair as _clock_only_lone_url_no_repair,
                latest_tool_json_since as _latest_tool_json_since,
                parse_get_current_time_json as _parse_get_current_time_json,
                post_tools_synthesis_needed as _post_tools_synthesis_needed,
                reply_is_tool_json_echo as _reply_is_tool_json_echo,
            )
            from duckclaw.forge.rag.prompt_policy import rag_turn_system_prompt
            from duckclaw.forge.rag.tool_policy import (
                should_prioritize_rag_over_storage_tools,
                without_storage_tools,
            )
            from duckclaw.graphs.proactive_review_markers import proactive_review_event_phrase_in_text
            from duckclaw.utils.logger import format_chat_log_identity, set_log_context
            from duckclaw.workers.db_intent_policy import (
                explicit_duckdb_schema_request,
                incoming_is_table_content_query as _incoming_is_table_content_query,
            )
            from duckclaw.workers.factory_agent_node_helpers import (
                _agent_node_llm_failure_user_message,
                _identity_fields,
                _last_human_message_index,
                _raise_if_chat_cancelled_from_state,
                _visual_asset_calls_since_last_human,
                _worker_log_label,
            )
            from duckclaw.workers.factory_graph_context import WorkerGraphContext
            from duckclaw.workers.factory_reddit_helpers import (
                _patch_reddit_get_post_args_from_canonical_url,
                _reddit_tools_paused,
                _resolve_reddit_share_url_to_comments_url,
            )
            from duckclaw.workers.provider_input_budget import apply_provider_input_budget as _apply_provider_input_budget
            from duckclaw.workers.runtime_policy_helpers import (
                worker_has_runtime_capability as _worker_has_runtime_capability,
                worker_use_heuristic_first_tool as _worker_use_heuristic_first_tool,
            )
            from duckclaw.workers.tool_binding import tool_called_since as _tool_called_since
            from duckclaw.workers.tool_invocation_policy import (
                decide_current_time_tool_invocation as _decide_current_time_tool_invocation,
                decide_db_first_tool_invocation as _decide_db_first_tool_invocation,
                decide_market_data_tool_invocation as _decide_market_data_tool_invocation,
            )
            from duckclaw.workers.tool_surface_policy import (
                should_hide_sandbox_tools,
                should_hide_storage_identity_tools,
                tool_surface_intent_text,
                without_privileged_mutation_tools,
                without_sandbox_tools,
                without_storage_identity_tools,
            )
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

            _log = logging.getLogger(__name__)


            def make_agent_invoke_node(ctx: WorkerGraphContext):
                {agent_unpack}
                def agent_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
            {AGENT_INVOKE_BODY}
                return agent_node
            '''
        ),
    )

    write(
        "factory_graph_nodes_agent.py",
        dedent(
            f'''
            """Agent node factory (no-LLM stub or invoke delegate)."""

            from __future__ import annotations

            from typing import Any, Optional

            try:
                from langchain_core.runnables import RunnableConfig
            except ImportError:
                RunnableConfig = Any  # type: ignore[misc, assignment]

            from duckclaw.workers.factory_agent_node_helpers import _identity_fields
            from duckclaw.workers.factory_graph_context import WorkerGraphContext
            from duckclaw.workers.factory_graph_nodes_agent_invoke import make_agent_invoke_node
            from langchain_core.messages import AIMessage


            def make_agent_node(ctx: WorkerGraphContext):
                if ctx.llm is None:
                    def agent_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
            {AGENT_NO_LLM}
                    return agent_node
                return make_agent_invoke_node(ctx)
            '''
        ),
    )

    tools_unpack = dedent(
        """
    worker_id = ctx.worker_id
    db = ctx.db
    spec = ctx.spec
    path = ctx.path
    shared_resolved = ctx.shared_resolved
    tools_by_name = ctx.tools_by_name
    tools_by_name_sandbox_off = ctx.tools_by_name_sandbox_off
    use_cm = ctx.use_context_monitor
    _sandbox_enabled_for_state = ctx.sandbox_enabled_for_state
    from duckclaw.workers import read_pool
"""
    )

    write(
        "factory_graph_nodes_tools.py",
        dedent(
            f'''
            """tools_node for worker LangGraph."""

            from __future__ import annotations

            import json
            import logging
            import time
            from concurrent.futures import ThreadPoolExecutor, as_completed
            from pathlib import Path
            from typing import Any, Optional

            try:
                from langchain_core.runnables import RunnableConfig
            except ImportError:
                RunnableConfig = Any  # type: ignore[misc, assignment]

            from duckclaw.utils.logger import format_chat_log_identity, set_log_context
            from duckclaw.workers.db_runtime import RUN_SANDBOX_TOOL_LLM_MAX_CHARS as _RUN_SANDBOX_TOOL_LLM_MAX_CHARS
            from duckclaw.workers.factory_agent_node_helpers import (
                _identity_fields,
                _raise_if_chat_cancelled_from_state,
                _worker_log_label,
            )
            from duckclaw.workers.factory_graph_context import WorkerGraphContext
            from duckclaw.workers.factory_sandbox_notify import (
                _heartbeat_elapsed_sec,
                _sandbox_heartbeat_allowed,
                _schedule_run_browser_novnc_tool_heartbeat,
                _send_sandbox_heartbeat_telegram,
            )
            from duckclaw.workers.skill_tool_registry import read_visual_artifact_image_as_b64 as _read_visual_artifact_image_as_b64
            from duckclaw.workers.tool_output_truncation import compact_run_sandbox_tool_content_for_llm as _compact_run_sandbox_tool_content_for_llm
            from langchain_core.messages import ToolMessage

            _log = logging.getLogger(__name__)


            def make_tools_node(ctx: WorkerGraphContext):
                {tools_unpack}
                def tools_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
            {TOOLS_BODY}
                return tools_node
            '''
        ),
    )

    set_reply_unpack = dedent(
        """
    worker_id = ctx.worker_id
    db = ctx.db
    spec = ctx.spec
    llm = ctx.llm
    tool_surface = ctx.tool_surface
    is_market_analysis_worker = ctx.is_market_analysis_worker
    tools_by_name = ctx.tools_by_name
    tools_by_name_sandbox_off = ctx.tools_by_name_sandbox_off
    use_cm = ctx.use_context_monitor
    _sandbox_enabled_for_state = ctx.sandbox_enabled_for_state
    from duckclaw.integrations.llm_providers import extract_embedded_tool_invokes
"""
    )

    write(
        "factory_graph_nodes_set_reply.py",
        dedent(
            f'''
            """set_reply node for worker LangGraph."""

            from __future__ import annotations

            import json
            import logging
            from typing import Any, Optional

            try:
                from langchain_core.runnables import RunnableConfig
            except ImportError:
                RunnableConfig = Any  # type: ignore[misc, assignment]

            from duckclaw.egress.tool_response_repair import (
                deterministic_tool_response_summary as _deterministic_tool_response_summary,
                repair_tool_response_egress_reply as _repair_tool_response_egress_reply,
                reply_is_tool_json_echo as _reply_is_tool_json_echo,
                tool_response_needs_egress_repair as _tool_response_needs_egress_repair,
            )
            from duckclaw.workers.factory_agent_node_helpers import (
                _identity_fields,
                _last_human_message_index,
                _spec_logical_worker_id,
            )
            from duckclaw.workers.factory_graph_context import WorkerGraphContext
            from duckclaw.workers.factory_sandbox_notify import _heartbeat_elapsed_sec
            from duckclaw.workers.visual_evidence_policy import visual_evidence_max_retries as _visual_evidence_max_retries

            _log = logging.getLogger(__name__)


            def make_set_reply_node(ctx: WorkerGraphContext):
                {set_reply_unpack}
                def set_reply(state: dict, config: Optional[RunnableConfig] = None) -> dict:
            {SET_REPLY_BODY}
                return set_reply
            '''
        ),
    )

    write(
        "factory_graph_nodes_routing.py",
        dedent(
            f'''
            """Routing nodes and conditional edge functions."""

            from __future__ import annotations

            from typing import Any, Optional

            try:
                from langchain_core.runnables import RunnableConfig
            except ImportError:
                RunnableConfig = Any  # type: ignore[misc, assignment]

            from duckclaw.workers.factory_graph_context import WorkerGraphContext


            def make_should_continue(ctx: WorkerGraphContext):
                def should_continue(state: dict) -> str:
            {ROUTING_SHOULD_CONTINUE}
                return should_continue


            def make_fact_check_node(ctx: WorkerGraphContext):
                llm = ctx.llm
                max_retries = ctx.context_guard_max_retries

                def fact_check_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
            {ROUTING_FACT_CHECK}
                return fact_check_node


            def make_self_correction_node(ctx: WorkerGraphContext):
                llm = ctx.llm

                def self_correction_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
            {ROUTING_SELF_CORRECTION}
                return self_correction_node


            def make_handoff_reply_node(ctx: WorkerGraphContext):
                def handoff_reply_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
            {ROUTING_HANDOFF}
                return handoff_reply_node


            def make_route_after_fact_check(ctx: WorkerGraphContext):
                def route_after_fact_check(state: dict) -> str:
            {ROUTING_AFTER_FACT}
                return route_after_fact_check


            def make_route_after_set_reply(ctx: WorkerGraphContext):
                def route_after_set_reply(state: dict) -> str:
            {ROUTING_AFTER_SET_REPLY}
                return route_after_set_reply


            def make_homeostasis_node(ctx: WorkerGraphContext):
                def homeostasis_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
            {ROUTING_HOMEOSTASIS}
                return homeostasis_node
            '''
        ),
    )

    write(
        "factory_graph_assembly.py",
        dedent(
            f'''
            """LangGraph wiring for worker templates."""

            from __future__ import annotations

            from pathlib import Path
            from typing import Any, Literal, Optional

            from duckclaw.workers.factory_graph_context import WorkerGraphContext
            from duckclaw.workers.factory_graph_nodes_agent import make_agent_node
            from duckclaw.workers.factory_graph_nodes_prepare import (
                make_prepare_node,
                make_sandbox_enabled_for_state,
            )
            from duckclaw.workers.factory_graph_nodes_routing import (
                make_fact_check_node,
                make_handoff_reply_node,
                make_homeostasis_node,
                make_route_after_fact_check,
                make_route_after_set_reply,
                make_self_correction_node,
                make_should_continue,
            )
            from duckclaw.workers.factory_graph_nodes_set_reply import make_set_reply_node
            from duckclaw.workers.factory_graph_nodes_tools import make_tools_node
            from duckclaw.workers.factory_graph_setup import initialize_worker_graph_context


            def build_worker_graph(
                worker_id: str,
                db_path: Optional[str],
                llm: Optional[Any],
                *,
                templates_root: Optional[Path] = None,
                instance_name: Optional[str] = None,
                llm_provider: Optional[str] = None,
                llm_model: Optional[str] = None,
                llm_base_url: Optional[str] = None,
                shared_db_path: Optional[str] = None,
                reuse_db: Any | None = None,
                tool_surface: Literal["full", "context_synthesis", "visual_generation", "url_research"] = "full",
                incoming_hint: str | None = None,
                open_vault_read_only: bool = False,
                db: Any | None = None,
                tenant_id: str = "default",
            ) -> Any:
                ctx = initialize_worker_graph_context(
                    worker_id,
                    db_path,
                    llm,
                    templates_root=templates_root,
                    instance_name=instance_name,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                    llm_base_url=llm_base_url,
                    shared_db_path=shared_db_path,
                    reuse_db=reuse_db,
                    tool_surface=tool_surface,
                    incoming_hint=incoming_hint,
                    open_vault_read_only=open_vault_read_only,
                    db=db,
                    tenant_id=tenant_id,
                )
                spec = ctx.spec
                db = ctx.db
                use_cm = ctx.use_context_monitor
                context_guard_enabled = ctx.context_guard_enabled

                ctx.sandbox_enabled_for_state = make_sandbox_enabled_for_state(ctx)
                prepare_node = make_prepare_node(ctx)
                context_monitor_node = ctx.context_monitor_node
                agent_node = make_agent_node(ctx)
                tools_node = make_tools_node(ctx)
                set_reply = make_set_reply_node(ctx)
                should_continue = make_should_continue(ctx)
                fact_check_node = make_fact_check_node(ctx)
                self_correction_node = make_self_correction_node(ctx)
                handoff_reply_node = make_handoff_reply_node(ctx)
                route_after_fact_check = make_route_after_fact_check(ctx)
                route_after_set_reply = make_route_after_set_reply(ctx)
                homeostasis_node = make_homeostasis_node(ctx)

                from langgraph.graph import END, StateGraph

            {ASSEMBLY_GRAPH}
            '''
        ),
    )

    write(
        "factory_graph_builder.py",
        dedent(
            '''
            """Thin re-export: LangGraph assembly for worker templates."""

            from duckclaw.workers.factory_graph_assembly import build_worker_graph

            __all__ = ["build_worker_graph"]
            '''
        ),
    )

    print("Done.")


if __name__ == "__main__":
    main()
