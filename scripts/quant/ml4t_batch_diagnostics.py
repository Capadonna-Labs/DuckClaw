#!/usr/bin/env python3
"""
Batch offline: métricas de cartera (ML4T PortfolioAnalysis) sobre retornos EW
construidos desde `quant_core.ohlcv_data` en DuckDB (solo lectura).

No ml4t-data. Uso: scripts/quant/run_ml4t_batch_docker.sh diagnostics …
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS_Q = Path(__file__).resolve().parent
if str(_SCRIPTS_Q) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_Q))

from ml4t.diagnostic.evaluation import PortfolioAnalysis
from ml4t.diagnostic.evaluation.stats import deflated_sharpe_ratio

from ml4t_batch_common import (
    equal_weight_daily_returns,
    json_sanitize,
    load_close_panel,
    validate_tickers,
)


def main() -> int:
    p = argparse.ArgumentParser(description="ML4T diagnostic sobre retornos EW desde DuckDB RO")
    p.add_argument("--duckdb-path", type=Path, required=True, help="Ruta DuckDB (solo lectura)")
    p.add_argument("--tickers", type=validate_tickers, required=True, help="CSV de tickers ej. SPY,TLT,IEF")
    p.add_argument("--max-rows-per-ticker", type=int, default=504, help="Barras diarias máx por ticker (default ~2y)")
    p.add_argument("--dsr-trials", type=int, default=50, help="n_trials para Deflated Sharpe")
    args = p.parse_args()

    db_path = args.duckdb_path.expanduser().resolve()
    if not db_path.is_file():
        print(json.dumps({"ok": False, "error": "duckdb no encontrado", "path": str(db_path)}), file=sys.stderr)
        return 2

    close = load_close_panel(str(db_path), args.tickers, max_rows_per_ticker=args.max_rows_per_ticker)
    if close.empty or close.shape[1] < len(args.tickers):
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "panel vacío o tickers ausentes",
                    "shape": getattr(close, "shape", None),
                    "wanted": args.tickers,
                }
            ),
            file=sys.stderr,
        )
        return 1

    ew = equal_weight_daily_returns(close)
    if ew.empty:
        print(json.dumps({"ok": False, "error": "retornos insuficientes"}), file=sys.stderr)
        return 1

    pa = PortfolioAnalysis(ew.astype(float))
    metrics = pa.compute_summary_stats()

    metrics_dict = {k: json_sanitize(getattr(metrics, k)) for k in sorted(vars(metrics)) if not k.startswith("_")}

    dsr_trials = int(os.environ.get("ML4T_DSR_TRIALS", args.dsr_trials))
    dsr_payload: dict[str, object] | None = None
    try:
        dsr_result = deflated_sharpe_ratio(
            returns=ew.to_numpy(dtype=float),
            benchmark_sharpe=float(os.environ.get("ML4T_DSR_BENCH", "0") or "0"),
            n_trials=max(10, min(dsr_trials, 5000)),
        )
        dsr_payload = {
            "sharpe_ratio": json_sanitize(getattr(dsr_result, "sharpe_ratio", None)),
            "deflated_sharpe": json_sanitize(getattr(dsr_result, "deflated_sharpe", None)),
            "is_significant": getattr(dsr_result, "is_significant", None),
        }
    except Exception as exc:
        dsr_payload = {"error": str(exc)[:240]}

    out = json_sanitize(
        {
            "ok": True,
            "strategy": "equal_weight_daily_from_quant_core_close",
            "n_observations": int(ew.shape[0]),
            "tickers_requested": args.tickers,
            "tickers_loaded": sorted(close.columns.astype(str)),
            "metrics": metrics_dict,
            "deflated_sharpe_summary": dsr_payload,
        }
    )
    print(json.dumps(out, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())