#!/usr/bin/env python3
"""
Batch offline: resumen vectorizado “buy & hold equal-weight” + métricas ML4T
sobre la serie de riqueza derivada de `quant_core.ohlcv_data`.

No es el motor event-driven completo de `ml4t.backtest.Engine` (pesado); usa
retornos EW diarios y `PortfolioAnalysis` como capa útil de métricas. Ingesta
sigue siendo DuckClaw — no ml4t-data.

Uso: scripts/quant/run_ml4t_batch_docker.sh backtest …
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_Q = Path(__file__).resolve().parent
if str(_SCRIPTS_Q) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_Q))

import pandas as pd
from ml4t.diagnostic.evaluation import PortfolioAnalysis

from ml4t_batch_common import (
    equal_weight_daily_returns,
    json_sanitize,
    load_close_panel,
    validate_tickers,
)


def _equity_curve_from_returns(daily: pd.Series) -> pd.Series:
    r = daily.astype(float).fillna(0.0)
    return (1.0 + r).cumprod()


def main() -> int:
    p = argparse.ArgumentParser(description="Vector EW backtest summary + ML4T metrics (DuckDB RO)")
    p.add_argument("--duckdb-path", type=Path, required=True)
    p.add_argument("--tickers", type=validate_tickers, required=True)
    p.add_argument("--max-rows-per-ticker", type=int, default=504)
    args = p.parse_args()

    db_path = args.duckdb_path.expanduser().resolve()
    if not db_path.is_file():
        print(json.dumps({"ok": False, "error": "duckdb no encontrado"}), file=sys.stderr)
        return 2

    close = load_close_panel(str(db_path), args.tickers, max_rows_per_ticker=args.max_rows_per_ticker)
    ew = equal_weight_daily_returns(close)
    if ew.empty:
        print(json.dumps({"ok": False, "error": "retornos insuficientes"}), file=sys.stderr)
        return 1

    eq = _equity_curve_from_returns(ew)
    total_return = float(eq.iloc[-1] - 1.0) if len(eq) else 0.0

    pa = PortfolioAnalysis(ew.astype(float))
    m = pa.compute_summary_stats()
    metrics = {k: json_sanitize(getattr(m, k)) for k in sorted(vars(m)) if not k.startswith("_")}

    per_ticker_bh: dict[str, float] = {}
    for col in close.columns:
        s = close[col].pct_change().dropna()
        if len(s) > 1:
            per_ticker_bh[str(col)] = float((1.0 + s).prod() - 1.0)

    out = json_sanitize(
        {
            "ok": True,
            "framework": "duckclaw.vector_ew",
            "note": "Motor event ml4t.backtest.Engine disponible en sandbox (reglas complejas); este job es vectorizado.",
            "n_days": int(ew.shape[0]),
            "tickers": args.tickers,
            "equal_weight_total_return": round(total_return, 6),
            "per_ticker_buy_hold_total_return": {k: round(v, 6) for k, v in sorted(per_ticker_bh.items())},
            "ml4t_portfolio_analysis": metrics,
            "engine_module": "ml4t.backtest",
        }
    )
    print(json.dumps(out, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())