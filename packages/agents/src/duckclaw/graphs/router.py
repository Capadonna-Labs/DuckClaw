"""
Entry router agent (LangGraph): single entrypoint for user messages.

State contract:
  - Input:  incoming (str), history (optional list of {role, content})
  - Internal: route ("retail" | "general")
  - Output:  reply (str, always present)

API: build_entry_router_graph(db, llm, *, store_db=None, console=None, system_prompt="",
  llm_provider="", llm_model="")
  returns a compiled LangGraph. Invoke with: graph.invoke({"incoming": text, "history": history or []}).
"""

from __future__ import annotations

import re
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig

from duckclaw.utils.langsmith_trace import get_tracing_config

# Keywords that indicate retail intent (inventario, ventas, gastos)
RETAIL_KEYWORDS = re.compile(
    r"\b(venta|vendí|vendimos|inventario|stock|qué hay|que queda|listar productos|"
    r"gasto|gastos|gastar|arriendo|servicios|registra venta|registrar venta|"
    r"precio|pagar|efectivo|tarjeta|transferencia|talla|xl|2xl|blusa|pantalón|camisa)\b",
    re.IGNORECASE,
)


def _route_by_keywords(incoming: str, has_retail: bool) -> Optional[str]:
    """Rule-based route. Returns 'retail' or 'general', or None if ambiguous."""
    if not has_retail:
        return "general"
    text = (incoming or "").strip()
    if not text:
        return "general"
    if RETAIL_KEYWORDS.search(text):
        return "retail"
    return "general"


def get_route(incoming: str, has_retail: bool) -> str:
    """Decide route: 'retail' or 'general'. has_retail: True if store_db is available."""
    return _route_by_keywords(incoming, has_retail) or "general"


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
    Build the entry LangGraph: route (hybrid) -> retail or general -> reply.

    State: incoming (str), history (optional list), route (internal), reply (output).
    """
    from langgraph.graph import END, StateGraph

    from duckclaw.graphs.general_graph import build_general_graph
    from duckclaw.graphs.retail_graph import build_retail_graph

    has_retail = store_db is not None

    retail_graph = (
        build_retail_graph(store_db or db, llm, console=console, system_prompt=system_prompt) if has_retail else None
    )
    general_graph = build_general_graph(db, llm, system_prompt=system_prompt)

    def route_node(state: dict) -> dict:
        incoming = (state.get("incoming") or "").strip()
        history = state.get("history") or []
        # 1) Rules first
        route = _route_by_keywords(incoming, has_retail)
        # 2) LLM fallback only when ambiguous (no keyword match and short/neutral message)
        if route == "general" and has_retail and _is_ambiguous(incoming):
            route = _route_by_llm(llm, incoming, history)
        out = {"route": route or "general", "incoming": incoming, "history": history}
        if "graph_context" in state:
            out["graph_context"] = state.get("graph_context") or ""
        return out

    def retail_node(state: dict, config: RunnableConfig) -> dict:
        assert retail_graph is not None
        tc = get_tracing_config("default", "router:retail", "unknown", base=config)
        result = retail_graph.invoke(
            {
                "incoming": state.get("incoming", ""),
            },
            tc,
        )
        return {"reply": result.get("reply") or "Sin respuesta."}

    def _store_name_from_prompt(prompt: str) -> str:
        """Extrae el nombre de la tienda del system_prompt (ej. 'asistente de Lumi Store')."""
        if not prompt:
            return "Lumi Store"
        m = re.search(r"asistente\s+de\s+([^,.\n]+?)(?:\s*,\s*una\s+tienda|\s*\.|$)", prompt, re.I)
        return (m.group(1).strip() or "Lumi Store") if m else "Lumi Store"

    def general_node(state: dict, config: RunnableConfig) -> dict:
        incoming = (state.get("incoming") or "").strip()
        # Preguntas sobre nombre de la tienda → respuesta directa
        if re.search(r"\b(nombre\s+de\s+la\s+tienda|c[oó]mo\s+se\s+llama\s+la\s+tienda|qu[eé]\s+tienda\s+es|nombre\s+tienda)\b", incoming, re.I):
            store = _store_name_from_prompt(system_prompt)
            return {"reply": f"La tienda se llama {store}."}
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
    graph.add_node("route", route_node)
    if has_retail:
        graph.add_node("retail", retail_node)
    graph.add_node("general", general_node)
    graph.set_entry_point("route")

    def after_route(state: dict) -> str:
        return state.get("route") or "general"

    if has_retail:
        graph.add_conditional_edges("route", after_route, {"retail": "retail", "general": "general"})
        graph.add_edge("retail", END)
    else:
        graph.add_edge("route", "general")
    graph.add_edge("general", END)

    return graph.compile()


def _is_ambiguous(text: str) -> bool:
    """Consider short or generic messages as ambiguous for routing."""
    t = (text or "").strip()
    if len(t) < 3:
        return False
    # Very short or greeting-like -> ambiguous
    if len(t) < 15 and re.match(r"^(hola|hey|buenas|qué tal|ayuda|help|que puedes)\b", t, re.I):
        return True
    return False


def _route_by_llm(llm: Any, incoming: str, history: list) -> str:
    """Use LLM to classify intent: retail vs general. Returns 'retail' or 'general'."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        system = (
            "Clasifica la intención del usuario en una sola palabra: 'retail' o 'general'. "
            "'retail' = ventas, inventario, gastos, productos, precios, tallas, pagos. "
            "'general' = consultas SQL, datos, tablas, otra cosa. Responde solo la palabra."
        )
        user = f"Mensaje: {incoming}"
        resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = (getattr(resp, "content", None) or str(resp)).strip().lower()
        if "retail" in content:
            return "retail"
    except Exception:
        pass
    return "general"
