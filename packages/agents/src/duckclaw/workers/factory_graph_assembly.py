"""LangGraph wiring for worker templates."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional

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
    max_tool_rounds: int | None = None,
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
    if max_tool_rounds is not None:
        ctx.max_tool_rounds = max(1, int(max_tool_rounds))
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


    graph = StateGraph(dict)
    graph.add_node("prepare", prepare_node)
    if use_cm:
        graph.add_node("context_monitor", context_monitor_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("set_reply", set_reply)
    if context_guard_enabled:
        graph.add_node("fact_check", fact_check_node)
        graph.add_node("self_correction", self_correction_node)
        graph.add_node("handoff_reply", handoff_reply_node)
    if getattr(spec, "homeostasis_config", None):
        graph.add_node("homeostasis", homeostasis_node)
        graph.set_entry_point("homeostasis")
        graph.add_edge("homeostasis", "prepare")
    else:
        graph.set_entry_point("prepare")
    if use_cm:
        graph.add_edge("prepare", "context_monitor")
        graph.add_edge("context_monitor", "agent")
    else:
        graph.add_edge("prepare", "agent")
    if context_guard_enabled:
        graph.add_conditional_edges(
            "agent", should_continue,
            {"tools": "tools", "end": "fact_check"},
        )
        graph.add_conditional_edges(
            "fact_check", route_after_fact_check,
            {"approved": "set_reply", "correct": "self_correction", "handoff": "handoff_reply"},
        )
        graph.add_edge("self_correction", "fact_check")
        graph.add_edge("handoff_reply", END)
    else:
        graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": "set_reply"})
    _tools_dest = "context_monitor" if use_cm else "agent"
    if use_cm:
        graph.add_edge("tools", "context_monitor")
    else:
        graph.add_edge("tools", "agent")
    graph.add_conditional_edges(
        "set_reply",
        route_after_set_reply,
        {"agent": "agent", "end": END},
    )

    compiled = graph.compile()
    compiled._worker_spec = spec
    compiled._worker_db = db
    return compiled
