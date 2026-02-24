"""BI helpers for DuckClaw: Olist dataset load, business queries, gráficas y agente con LLM (Groq)."""

from duckclaw.bi.olist import (
    load_olist_data,
    get_top_customers_by_sales,
    get_customers_to_retain,
    get_top_sellers,
    get_delivery_metrics,
    get_delivery_critical_cases,
    get_sales_summary,
    get_review_metrics,
    get_category_sales,
)

__all__ = [
    "load_olist_data",
    "get_top_customers_by_sales",
    "get_customers_to_retain",
    "get_top_sellers",
    "get_delivery_metrics",
    "get_delivery_critical_cases",
    "get_sales_summary",
    "get_review_metrics",
    "get_category_sales",
    "plot_category_sales_bar",
    "plot_top_sellers_bar",
    "plot_review_score_pie",
    "plot_delivery_days_histogram",
    "plot_top_customers_bar",
    "ask_bi",
    "build_bi_graph",
    "build_olist_bi_tools",
]


def __getattr__(name: str):
    if name in ("ask_bi", "build_bi_graph", "build_olist_bi_tools"):
        from duckclaw.bi import agent
        return getattr(agent, name)
    if name in (
        "plot_category_sales_bar",
        "plot_top_sellers_bar",
        "plot_review_score_pie",
        "plot_delivery_days_histogram",
        "plot_top_customers_bar",
    ):
        from duckclaw.bi import plots
        return getattr(plots, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
