"""
Agente BI Olist: LLM (p. ej. Groq) interpreta preguntas en lenguaje natural
y usa las funciones DuckClaw de duckclaw.bi.olist como tools.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from duckclaw.bi import olist as bi_olist


def _result_to_str(data: list[dict[str, Any]]) -> str:
    """Serializa resultado de una función BI para el LLM."""
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def build_olist_bi_tools(db: Any) -> list[Any]:
    """Construye herramientas LangChain para las funciones BI Olist (DuckClaw)."""
    from langchain_core.tools import StructuredTool

    def _safe(fn: Any, *args: Any, **kwargs: Any) -> str:
        """Evita que una falla SQL rompa el grafo; devuelve error legible."""
        try:
            data = fn(*args, **kwargs)
            return _result_to_str(data)
        except Exception as e:
            return f"Error ejecutando herramienta BI: {e}"

    def top_customers(limit: int = 15) -> str:
        """Clientes que más generan ventas. Argumento: limit (número de clientes, ej. 15)."""
        return _safe(bi_olist.get_top_customers_by_sales, db, limit=limit)

    def customers_to_retain(limit: int = 15, min_orders: int = 2) -> str:
        """Clientes a fidelizar (recurrentes, varios pedidos). Argumentos: limit, min_orders (mínimo de pedidos)."""
        return _safe(
            bi_olist.get_customers_to_retain, db, limit=limit, min_orders=min_orders
        )

    def top_sellers(limit: int = 15) -> str:
        """Mejores vendedores por ventas. Argumento: limit."""
        return _safe(bi_olist.get_top_sellers, db, limit=limit)

    def delivery_metrics() -> str:
        """Promedio y min/max de días de entrega (pedidos entregados)."""
        return _safe(bi_olist.get_delivery_metrics, db)

    def delivery_critical(days_threshold: int = 20, limit: int = 30) -> str:
        """Entregas críticas (más de X días). Argumentos: days_threshold (ej. 20), limit."""
        return _safe(
            bi_olist.get_delivery_critical_cases,
            db,
            days_threshold=days_threshold,
            limit=limit,
        )

    def sales_summary() -> str:
        """Resumen de ventas: total pedidos, ventas totales, ticket promedio."""
        return _safe(bi_olist.get_sales_summary, db)

    def review_metrics() -> str:
        """Métricas de satisfacción: puntuación media y buenas/malas reviews."""
        return _safe(bi_olist.get_review_metrics, db)

    def category_sales(limit: int = 15) -> str:
        """Ventas por categoría de producto. Argumento: limit."""
        return _safe(bi_olist.get_category_sales, db, limit=limit)

    # Herramientas de gráficas (matplotlib/seaborn)
    try:
        from duckclaw.bi import plots as bi_plots
        _save = "output"

        def plot_categories(limit: int = 12) -> str:
            """Genera gráfico de barras de ventas por categoría. Usar cuando pidan gráfica de categorías o ventas por tipo de producto."""
            return bi_plots.plot_category_sales_bar(db, save_dir=_save, limit=limit)

        def plot_sellers(limit: int = 10) -> str:
            """Genera gráfico de barras de mejores vendedores. Usar cuando pidan gráfica de vendedores."""
            return bi_plots.plot_top_sellers_bar(db, save_dir=_save, limit=limit)

        def plot_reviews_pie() -> str:
            """Genera gráfico de torta de puntuaciones de reviews. Usar cuando pidan gráfica de valoraciones o satisfacción."""
            return bi_plots.plot_review_score_pie(db, save_dir=_save)

        def plot_delivery_hist() -> str:
            """Genera histograma de días de entrega. Usar cuando pidan gráfica de tiempos de entrega."""
            return bi_plots.plot_delivery_days_histogram(db, save_dir=_save)

        def plot_customers_bar(limit: int = 10) -> str:
            """Genera gráfico de barras de clientes que más ventas generan. Usar cuando pidan gráfica de clientes top."""
            return bi_plots.plot_top_customers_bar(db, save_dir=_save, limit=limit)

        plot_tools = [
            StructuredTool.from_function(
                func=plot_categories,
                name="plot_category_sales_bar",
                description="Genera y guarda un gráfico de barras de ventas por categoría. Usar cuando pidan gráfica, chart o visualización de categorías o ventas por producto.",
            ),
            StructuredTool.from_function(
                func=plot_sellers,
                name="plot_top_sellers_bar",
                description="Genera y guarda un gráfico de barras de mejores vendedores. Usar cuando pidan gráfica de vendedores.",
            ),
            StructuredTool.from_function(
                func=plot_reviews_pie,
                name="plot_review_score_pie",
                description="Genera y guarda un gráfico de torta de puntuaciones de reviews. Usar cuando pidan gráfica de valoraciones o satisfacción.",
            ),
            StructuredTool.from_function(
                func=plot_delivery_hist,
                name="plot_delivery_days_histogram",
                description="Genera y guarda un histograma de días de entrega. Usar cuando pidan gráfica de tiempos o plazos de entrega.",
            ),
            StructuredTool.from_function(
                func=plot_customers_bar,
                name="plot_top_customers_bar",
                description="Genera y guarda un gráfico de barras de clientes que más ventas generan. Usar cuando pidan gráfica de clientes top.",
            ),
        ]
    except Exception:
        plot_tools = []

    return [
        StructuredTool.from_function(
            func=top_customers,
            name="get_top_customers_by_sales",
            description="Lista los clientes que más ventas generan (por valor total). Usar cuando pregunten quiénes son los mejores clientes, quiénes más compran, o clientes top por ventas.",
        ),
        StructuredTool.from_function(
            func=customers_to_retain,
            name="get_customers_to_retain",
            description="Clientes candidatos a fidelizar: con varios pedidos y buen valor. Usar para fidelización, clientes recurrentes, a quiénes retener.",
        ),
        StructuredTool.from_function(
            func=top_sellers,
            name="get_top_sellers",
            description="Mejores vendedores por valor vendido. Usar para mejores vendedores, ranking de sellers.",
        ),
        StructuredTool.from_function(
            func=delivery_metrics,
            name="get_delivery_metrics",
            description="Promedio, mínimo y máximo de días de entrega. Usar para tiempo de entrega promedio, plazos de entrega.",
        ),
        StructuredTool.from_function(
            func=delivery_critical,
            name="get_delivery_critical_cases",
            description="Pedidos con entrega muy tardía (más de X días). Usar para casos críticos, entregas atrasadas, retrasos.",
        ),
        StructuredTool.from_function(
            func=sales_summary,
            name="get_sales_summary",
            description="Resumen ejecutivo: total pedidos, ventas totales, ticket promedio. Usar para resumen de ventas, KPIs globales.",
        ),
        StructuredTool.from_function(
            func=review_metrics,
            name="get_review_metrics",
            description="Satisfacción: nota media y cantidad de reviews buenas/malas. Usar para valoraciones, satisfacción, reviews.",
        ),
        StructuredTool.from_function(
            func=category_sales,
            name="get_category_sales",
            description="Ventas por categoría de producto. Usar para categorías más vendidas, ventas por tipo de producto.",
        ),
    ] + plot_tools


SYSTEM_PROMPT_BI = """Eres un analista BI para una tienda online (dataset Olist). Respondes en español.

Tienes herramientas de datos (get_*) y de gráficas (plot_*). Las gráficas se guardan en la carpeta "output"; indica al usuario la ruta del archivo generado.

Cuando pregunten en lenguaje natural:
1. Si piden números o resúmenes: usa get_top_customers_by_sales, get_customers_to_retain, get_top_sellers, get_delivery_metrics, get_delivery_critical_cases, get_sales_summary, get_review_metrics, get_category_sales.
2. Si piden gráfica, gráfico, chart o visualización: usa plot_category_sales_bar, plot_top_sellers_bar, plot_review_score_pie, plot_delivery_days_histogram o plot_top_customers_bar según corresponda.
3. Resume los resultados de forma clara. No pegues JSON crudo. Si generaste una gráfica, di en qué archivo se guardó (ej. output/ventas_por_categoria.png).
"""


def _last_ai_content(messages: list) -> str:
    """Extrae el contenido del último mensaje AI (no tool call)."""
    for m in reversed(messages):
        if not hasattr(m, "content") or not m.content:
            continue
        kind = getattr(m, "type", "") or getattr(m.__class__, "__name__", "")
        if kind == "ai" or "AIMessage" in str(kind):
            if not getattr(m, "tool_calls", None):
                return (m.content or "").strip()
    return ""


def build_bi_graph(
    db: Any,
    llm: Any,
    *,
    system_prompt: str = "",
) -> Any:
    """
    Grafo LangGraph: pregunta del usuario → LLM con tools BI Olist → respuesta.

    Estado: incoming (str), opcional history. Salida: reply (str).
    """
    from langgraph.graph import END, StateGraph
    from langgraph.prebuilt import create_react_agent

    tools = build_olist_bi_tools(db)
    prompt = (system_prompt or SYSTEM_PROMPT_BI).strip()
    # Compatible con LangGraph nuevo (prompt=) y antiguo (state_modifier=)
    try:
        agent = create_react_agent(llm, tools, prompt=prompt)
    except TypeError:
        agent = create_react_agent(llm, tools, state_modifier=prompt)

    def wrap_invoke(state: dict) -> dict:
        incoming = (state.get("incoming") or "").strip()
        result = agent.invoke({"messages": incoming})
        messages = result.get("messages") or []
        reply = _last_ai_content(messages)
        return {"reply": reply or "No hubo respuesta."}

    graph = StateGraph(dict)
    graph.add_node("agent", wrap_invoke)
    graph.set_entry_point("agent")
    graph.add_edge("agent", END)
    return graph.compile()


def ask_bi(
    db: Any,
    question: str,
    *,
    llm: Optional[Any] = None,
    provider: str = "groq",
    model: str = "",
) -> str:
    """
    Pregunta en lenguaje natural al agente BI (una sola llamada).

    - db: DuckClaw con datos Olist ya cargados (load_olist_data).
    - question: texto en lenguaje natural.
    - llm: si se pasa, se usa este LLM; si no, se construye uno con build_llm(provider, model).
    - provider: "groq" por defecto (requiere GROQ_API_KEY).
    - model: modelo Groq (por defecto llama-3.3-70b-versatile).

    Devuelve la respuesta en texto.
    """
    # Validación rápida de tablas mínimas para evitar errores SQL opacos
    try:
        import json as _json
        _tbls = db.query(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' ORDER BY table_name"
        )
        _names = {r.get("table_name") for r in (_json.loads(_tbls) if isinstance(_tbls, str) else (_tbls or []))}
        _required = {"olist_orders", "olist_order_items", "olist_sellers"}
        if not _required.issubset(_names):
            return (
                "Faltan tablas Olist en la base. Ejecuta primero "
                "`load_olist_data(db, <ruta_data>)` y verifica que cargue correctamente."
            )
    except Exception:
        pass

    if llm is None:
        from duckclaw.integrations.llm_providers import build_llm
        llm = build_llm(provider, model or "")
    graph = build_bi_graph(db, llm)
    result = graph.invoke({"incoming": question})
    return result.get("reply") or ""
