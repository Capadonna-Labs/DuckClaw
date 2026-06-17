"""Assembles and compiles the manager LangGraph."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from langgraph.graph import END, StateGraph

from duckclaw.graphs.state import ManagerAgentState
from duckclaw.manager.manager_graph_routing import (
    route_after_invoke_worker,
    route_after_plan,
    route_after_router,
)
from duckclaw.manager.manager_nodes_greeting import build_greeting_shortcut_node
from duckclaw.manager.manager_nodes_invoke import build_invoke_worker_node
from duckclaw.manager.manager_nodes_mercenary import build_mercenary_node
from duckclaw.manager.manager_nodes_plan import build_plan_node
from duckclaw.manager.manager_nodes_return import build_return_to_source_node
from duckclaw.manager.manager_nodes_router import build_router_node


def build_manager_graph(
    db: Any,
    llm: Optional[Any] = None,
    *,
    templates_root: Optional[Path] = None,
    db_path: Optional[str] = None,
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    planner_system_prompt: str = "",
) -> Any:
    """
    Construye el grafo manager: router -> invoke_worker.
    db: DuckClaw para agent_config y task_audit_log.
    """
    if db_path is None:
        try:
            from duckclaw.gateway_db import get_gateway_db_path

            db_path = get_gateway_db_path()
        except Exception:
            db_path = ""

    troot = templates_root
    resolved_db_path = db_path or ""

    router_node = build_router_node(db=db, troot=troot)
    greeting_shortcut_node = build_greeting_shortcut_node(db=db)
    plan_node = build_plan_node(
        db=db,
        llm=llm,
        troot=troot,
        planner_system_prompt=planner_system_prompt,
    )
    invoke_worker_node = build_invoke_worker_node(
        db=db,
        llm=llm,
        troot=troot,
        db_path=resolved_db_path,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
    )
    mercenary_node = build_mercenary_node(db=db)
    return_to_source_node = build_return_to_source_node(db=db)

    graph = StateGraph(ManagerAgentState)
    graph.add_node("router", router_node)
    graph.add_node("greeting_shortcut", greeting_shortcut_node)
    graph.add_node("plan", plan_node)
    graph.add_node("mercenary", mercenary_node)
    graph.add_node("invoke_worker", invoke_worker_node)
    graph.add_node("return_to_source", return_to_source_node)
    graph.set_entry_point("router")
    graph.add_conditional_edges(
        "router",
        route_after_router,
        {"greeting_shortcut": "greeting_shortcut", "plan": "plan"},
    )
    graph.add_edge("greeting_shortcut", END)
    graph.add_conditional_edges(
        "plan",
        route_after_plan,
        {"mercenary": "mercenary", "invoke_worker": "invoke_worker"},
    )
    graph.add_edge("mercenary", END)
    graph.add_conditional_edges(
        "invoke_worker",
        route_after_invoke_worker,
        {
            "return_to_source": "return_to_source",
            "plan": "plan",
            "end": END,
        },
    )
    graph.add_edge("return_to_source", "invoke_worker")
    return graph.compile()


__all__ = ["build_manager_graph"]
