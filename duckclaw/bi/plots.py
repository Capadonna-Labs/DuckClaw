"""
Gráficas con DuckClaw: matplotlib y seaborn a partir de datos Olist.

Uso en notebooks:
    from duckclaw.bi import plot_category_sales_bar, plot_top_sellers_bar, ...
    plot_category_sales_bar(db, save_dir="output")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


def _ensure_save_dir(save_dir: str) -> Path:
    p = Path(save_dir).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _get_data(db: Any, getter: Any, **kwargs: Any) -> list[dict]:
    import json
    raw = getter(db, **kwargs)
    if isinstance(raw, str):
        return json.loads(raw) if raw.strip().startswith("[") else []
    return list(raw) if raw else []


def plot_category_sales_bar(
    db: Any,
    save_dir: str = "output",
    limit: int = 12,
    filename: str = "ventas_por_categoria.png",
) -> str:
    """Gráfico de barras: ventas por categoría de producto (matplotlib)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return "Error: instala matplotlib (pip install matplotlib)"
    from duckclaw.bi.olist import get_category_sales
    data = _get_data(db, get_category_sales, limit=limit)
    if not data:
        return "No hay datos para graficar."
    labels = [d.get("category", "N/A")[:20] for d in data]
    values = [float(d.get("total_sales", 0)) for d in data]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(range(len(labels)), values, color="steelblue", alpha=0.85)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Ventas totales")
    ax.set_title("Ventas por categoría de producto")
    fig.tight_layout()
    out = _ensure_save_dir(save_dir) / filename
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return f"Gráfica guardada: {out}"


def plot_top_sellers_bar(
    db: Any,
    save_dir: str = "output",
    limit: int = 10,
    filename: str = "top_vendedores.png",
) -> str:
    """Gráfico de barras: mejores vendedores por ventas (matplotlib)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return "Error: instala matplotlib (pip install matplotlib)"
    from duckclaw.bi.olist import get_top_sellers
    data = _get_data(db, get_top_sellers, limit=limit)
    if not data:
        return "No hay datos para graficar."
    labels = [f"{d.get('seller_city','')} ({d.get('seller_id','')[:8]}...)" for d in data]
    values = [float(d.get("total_sales", 0)) for d in data]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(range(len(labels)), values, color="coral", alpha=0.85)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Ventas totales")
    ax.set_title("Top vendedores por ventas")
    fig.tight_layout()
    out = _ensure_save_dir(save_dir) / filename
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return f"Gráfica guardada: {out}"


def plot_review_score_pie(
    db: Any,
    save_dir: str = "output",
    filename: str = "reviews_puntuacion.png",
) -> str:
    """Gráfico de torta: distribución de puntuaciones de reviews (matplotlib)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return "Error: instala matplotlib (pip install matplotlib)"
    import json
    raw = db.query(
        "SELECT review_score, COUNT(*) AS n FROM olist_order_reviews GROUP BY review_score ORDER BY review_score"
    )
    rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    if not rows:
        return "No hay datos para graficar."
    labels = [f"Puntuación {r.get('review_score', '')}" for r in rows]
    sizes = [int(r.get("n", 0)) for r in rows]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=90, colors=plt.cm.Pastel1.colors)
    ax.set_title("Distribución de puntuaciones de reviews")
    fig.tight_layout()
    out = _ensure_save_dir(save_dir) / filename
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return f"Gráfica guardada: {out}"


def plot_delivery_days_histogram(
    db: Any,
    save_dir: str = "output",
    filename: str = "dias_entrega_histograma.png",
) -> str:
    """Histograma: días de entrega (seaborn si está, si no matplotlib)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return "Error: instala matplotlib (pip install matplotlib)"
    import json
    sql = """
    WITH t AS (
        SELECT DATE_DIFF('day', order_purchase_timestamp::TIMESTAMP, order_delivered_customer_date::TIMESTAMP) AS days
        FROM olist_orders
        WHERE order_status = 'delivered' AND order_delivered_customer_date IS NOT NULL
          AND order_purchase_timestamp IS NOT NULL
    )
    SELECT days FROM t WHERE days <= 60
    """
    raw = db.query(sql)
    rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    if not rows:
        return "No hay datos para graficar."
    days = [float(r.get("days", 0)) for r in rows]
    fig, ax = plt.subplots(figsize=(8, 4))
    try:
        import seaborn as sns
        sns.histplot(days, bins=30, kde=True, ax=ax, color="teal", alpha=0.7)
    except ImportError:
        ax.hist(days, bins=30, color="teal", alpha=0.7, edgecolor="white")
    ax.set_xlabel("Días de entrega")
    ax.set_ylabel("Cantidad de pedidos")
    ax.set_title("Distribución de días de entrega (hasta 60 días)")
    fig.tight_layout()
    out = _ensure_save_dir(save_dir) / filename
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return f"Gráfica guardada: {out}"


def plot_top_customers_bar(
    db: Any,
    save_dir: str = "output",
    limit: int = 10,
    filename: str = "top_clientes_ventas.png",
) -> str:
    """Gráfico de barras: clientes que más ventas generan (matplotlib)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return "Error: instala matplotlib (pip install matplotlib)"
    from duckclaw.bi.olist import get_top_customers_by_sales
    data = _get_data(db, get_top_customers_by_sales, limit=limit)
    if not data:
        return "No hay datos para graficar."
    labels = [f"{d.get('customer_city','')} ({d.get('customer_state','')})" for d in data]
    values = [float(d.get("total_sales", 0)) for d in data]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(range(len(labels)), values, color="mediumseagreen", alpha=0.85)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Ventas totales")
    ax.set_title("Clientes que más ventas generan")
    fig.tight_layout()
    out = _ensure_save_dir(save_dir) / filename
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return f"Gráfica guardada: {out}"
