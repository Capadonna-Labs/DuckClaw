"""
Plantilla de referencia — HRP rebalance para `execute_sandbox_script`.

Uso esperado:
- Copia este script como `code` dentro de la tool del sandbox.
- Reemplaza `PRICE_SERIES` con precios de cierre ya obtenidos en host.
- No lee DuckDB del host; todo se calcula en el contenedor del sandbox.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

# -------------------------------------------------------------------
# INPUTS (rellenar en runtime por el agente)
# -------------------------------------------------------------------
# Dict[ticker, List[close_price]]
PRICE_SERIES: dict[str, list[float]] = {
    "AAPL": [188.1, 189.4, 190.2, 191.5, 192.7, 191.8, 193.1],
    "MSFT": [411.3, 412.1, 413.8, 414.2, 416.0, 415.3, 417.1],
    "NVDA": [901.2, 908.4, 915.6, 920.1, 926.0, 931.2, 940.7],
}

# Pesos actuales de cartera (0..1). Si un ticker falta, asume 0.
CURRENT_WEIGHTS: dict[str, float] = {
    "AAPL": 0.30,
    "MSFT": 0.45,
    "NVDA": 0.25,
}

# Umbral para considerar señal de rebalanceo.
REBALANCE_THRESHOLD = 0.03


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    clipped = {k: max(float(v), 0.0) for k, v in weights.items()}
    total = float(sum(clipped.values()))
    if total <= 0:
        n = max(1, len(clipped))
        return {k: 1.0 / n for k in clipped}
    return {k: v / total for k, v in clipped.items()}


def _manual_hrp_weights(returns_df: pd.DataFrame) -> dict[str, float]:
    from scipy.cluster.hierarchy import linkage
    from scipy.spatial.distance import squareform

    cov = returns_df.cov()
    corr = returns_df.corr()
    # Distancia usada por HRP de López de Prado.
    dist = np.sqrt(np.clip((1.0 - corr.values) / 2.0, 0.0, 1.0))
    condensed = squareform(dist, checks=False)
    link = linkage(condensed, method="single")

    n = len(cov.columns)

    def _get_quasi_diag(linkage_matrix: np.ndarray) -> list[int]:
        sort_ix = pd.Series([linkage_matrix[-1, 0], linkage_matrix[-1, 1]])
        num_items = linkage_matrix[-1, 3]
        while sort_ix.max() >= num_items:
            sort_ix.index = range(0, sort_ix.shape[0] * 2, 2)
            df0 = sort_ix[sort_ix >= num_items]
            i = df0.index
            j = (df0.values - num_items).astype(int)
            sort_ix.loc[i] = linkage_matrix[j, 0]
            df1 = pd.Series(linkage_matrix[j, 1], index=i + 1)
            sort_ix = pd.concat([sort_ix, df1]).sort_index()
            sort_ix.index = range(sort_ix.shape[0])
        return sort_ix.astype(int).tolist()

    def _cluster_var(cov_mat: pd.DataFrame, cluster_items: list[str]) -> float:
        c = cov_mat.loc[cluster_items, cluster_items]
        inv_diag = 1.0 / np.diag(c.values)
        w = inv_diag / inv_diag.sum()
        return float(np.dot(w, np.dot(c.values, w)))

    sorted_idx = _get_quasi_diag(link)
    sorted_tickers = [cov.columns[i] for i in sorted_idx if i < n]
    weights = pd.Series(1.0, index=sorted_tickers)
    clusters: list[list[str]] = [sorted_tickers]

    while clusters:
        new_clusters: list[list[str]] = []
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            split = len(cluster) // 2
            c1 = cluster[:split]
            c2 = cluster[split:]
            v1 = _cluster_var(cov, c1)
            v2 = _cluster_var(cov, c2)
            alpha = 1.0 - v1 / max(v1 + v2, 1e-12)
            weights[c1] *= alpha
            weights[c2] *= 1.0 - alpha
            new_clusters.extend([c1, c2])
        clusters = new_clusters

    return _normalize(weights.to_dict())


def compute_hrp_targets(returns_df: pd.DataFrame) -> tuple[dict[str, float], str]:
    # Ruta preferida por policy del Quant-Trader.
    try:
        from pypfopt import HRPOpt
        from pypfopt import risk_models

        cov = risk_models.sample_cov(returns_df)
        hrp = HRPOpt(returns=returns_df, cov_matrix=cov)
        target = hrp.optimize()
        return _normalize(target), "pypfopt"
    except Exception:
        return _manual_hrp_weights(returns_df), "manual_scipy"


def main() -> None:
    prices = pd.DataFrame(PRICE_SERIES).dropna(how="all")
    prices = prices.apply(pd.to_numeric, errors="coerce").dropna(how="any")
    if prices.shape[0] < 4 or prices.shape[1] < 2:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "Datos insuficientes para HRP (min: 4 filas y 2 activos).",
                },
                ensure_ascii=False,
            )
        )
        return

    returns_df = prices.pct_change().dropna(how="any")
    target_weights, method = compute_hrp_targets(returns_df)

    tickers = sorted(target_weights.keys())
    current = {t: float(CURRENT_WEIGHTS.get(t, 0.0)) for t in tickers}
    current = _normalize(current)
    deltas = {t: target_weights[t] - current.get(t, 0.0) for t in tickers}
    max_abs_delta = max(abs(v) for v in deltas.values()) if deltas else 0.0

    print(
        json.dumps(
            {
                "ok": True,
                "method": method,
                "tickers": tickers,
                "target_weights": target_weights,
                "current_weights": current,
                "weight_deltas": deltas,
                "max_abs_delta": max_abs_delta,
                "rebalance_required": bool(max_abs_delta >= REBALANCE_THRESHOLD),
                "threshold": REBALANCE_THRESHOLD,
                "n_obs": int(returns_df.shape[0]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
