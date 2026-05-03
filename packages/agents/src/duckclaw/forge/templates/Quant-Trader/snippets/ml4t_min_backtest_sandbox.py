# Snippet sandbox: resumen vector EW + Deflated Sharpe (ML4T) sin motor event-driven pesado.
#
# Sustituir `closes_by_ticker`: dict[ticker] -> lista de cierres ASC (host embebe desde evidencia OHLCV mismo turno).
# Sin ml4t-data; política Quant sin red outbound por defecto.
import json

import pandas as pd
from ml4t.diagnostic.evaluation import PortfolioAnalysis
from ml4t.diagnostic.evaluation.stats import deflated_sharpe_ratio

closes_by_ticker: dict[str, list[float]] = {}  # noqa: modelo reemplaza desde host

def main() -> None:
    df = pd.DataFrame(closes_by_ticker).apply(pd.to_numeric, errors="coerce").dropna(how="any")
    if df.shape[0] < 22 or df.shape[1] < 1:
        raise SystemExit(json.dumps({"ok": False, "error": "closes panel too small"}, ensure_ascii=False))
    ew = df.pct_change().dropna(how="any").mean(axis=1).astype(float)
    summary = PortfolioAnalysis(ew).compute_summary_stats()
    metrics = {
        k: getattr(summary, k) for k in sorted(vars(summary)) if not str(k).startswith("_")
    }
    dsr = deflated_sharpe_ratio(returns=ew.to_numpy(dtype=float), benchmark_sharpe=0.0, n_trials=50)
    print(
        json.dumps(
            {
                "ok": True,
                "mode": "vector_ew_ml4t",
                "tickers_used": sorted(df.columns.astype(str)),
                "portfolio_metrics": metrics,
                "deflated_sharpe": float(getattr(dsr, "deflated_sharpe", 0.0)),
                "sharpe": float(getattr(dsr, "sharpe_ratio", 0.0)),
                "significant": bool(getattr(dsr, "is_significant", False)),
            },
            ensure_ascii=False,
            default=float,
        )
    )


if __name__ == "__main__":
    main()