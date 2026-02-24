"""
Entry router agent (LangGraph): single entrypoint for user messages.

State contract:
  - Input:  incoming (str), history (optional list of {role, content})
  - Internal: route ("retail" | "general")
  - Output:  reply (str, always present)

API: build_entry_router_graph(db, llm, *, store_db=None, console=None, system_prompt="")
  returns a compiled LangGraph. Invoke with: graph.invoke({"incoming": text, "history": history or []}).
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Keywords that indicate retail intent (finanzas, inventario, ventas, gastos)
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
) -> Any:
    """
    Build the entry LangGraph: route (hybrid) -> retail or general -> reply.

    State: incoming (str), history (optional list), route (internal), reply (output).
    """
    from langgraph.graph import END, StateGraph

    from duckclaw.agents.general_graph import build_general_graph
    from duckclaw.agents.retail_graph import build_retail_graph

    has_retail = store_db is not None
    retail_graph = (
        build_retail_graph(store_db or db, llm, console=console) if has_retail else None
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
        return {"route": route or "general"}

    def retail_node(state: dict) -> dict:
        result = retail_graph.invoke({
            "incoming": state.get("incoming", ""),
        })
        return {"reply": result.get("reply") or "Sin respuesta."}

    def general_node(state: dict) -> dict:
        result = general_graph.invoke({
            "incoming": state.get("incoming", ""),
            "history": state.get("history") or [],
        })
        return {"reply": result.get("reply") or "Sin respuesta."}

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
