"""
Entry router agent (LangGraph): single entrypoint for user messages.

State contract:
  - Input:  incoming (str), history (optional list of {role, content})
  - Output:  reply (str, always present)

API: build_entry_router_graph(db, llm, *, store_db=None, console=None, system_prompt="",
  llm_provider="", llm_model="")
  returns a compiled LangGraph. Invoke with: graph.invoke({"incoming": text, "history": history or []}).
"""

from __future__ import annotations

from typing import Any, Optional

from langchain_core.runnables import RunnableConfig

from duckclaw.utils.langsmith_trace import get_tracing_config


def build_entry_router_graph(
    db: Any,
    llm: Any,
    *,
    store_db: Optional[Any] = None,
    console: Optional[Any] = None,
    system_prompt: str = "",
    llm_provider: str = "",
    llm_model: str = "",
    save_traces: bool = False,
    send_to_langsmith: bool = False,
) -> Any:
    """
    Build the entry LangGraph: thin wrapper over general_graph.

    State: incoming (str), history (optional list), reply (output).
    store_db and console are accepted for backward compatibility but ignored.
    """
    from langgraph.graph import END, StateGraph

    from duckclaw.graphs.general_graph import build_general_graph

    _ = store_db, console, llm_provider, llm_model, save_traces, send_to_langsmith

    general_graph = build_general_graph(db, llm, system_prompt=system_prompt)

    def general_node(state: dict, config: RunnableConfig) -> dict:
        incoming = (state.get("incoming") or "").strip()
        tc = get_tracing_config("default", "router:general", "unknown", base=config)
        result = general_graph.invoke(
            {
                "incoming": incoming,
                "history": state.get("history") or [],
                "graph_context": state.get("graph_context") or "",
            },
            tc,
        )
        out = {"reply": result.get("reply") or "Sin respuesta."}
        if result.get("messages"):
            out["messages"] = result["messages"]
        return out

    graph = StateGraph(dict)
    graph.add_node("general", general_node)
    graph.set_entry_point("general")
    graph.add_edge("general", END)

    return graph.compile()
