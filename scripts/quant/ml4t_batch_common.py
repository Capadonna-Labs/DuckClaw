#!/usr/bin/env python3
"""
Utilidades ML4T batch: leer OHLCV desde DuckClaw (`quant_core.ohlcv_data`) solo lectura.

No usa ml4t-data — la fuente de precios sigue siendo ingestión Duck existente + DuckDB RO.
Ejecutación recomendada: `scripts/quant/run_ml4t_batch_docker.sh`.
"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

import duckdb
import pandas as pd


_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,32}$")


def validate_tickers(raw: str) -> list[str]:
    parts = [p.strip().upper() for p in raw.replace(";", ",").split(",") if p.strip()]
    out: list[str] = []
    for p in parts:
        if not _TICKER_RE.match(p):
            raise argparse.ArgumentTypeError(f"ticker inválido: {p!r}")
        out.append(p)
    if len(out) < 1:
        raise argparse.ArgumentTypeError("--tickers debe listar ≥1 símbolo")
    return sorted(set(out))


def load_close_panel(db_path: str, tickers: list[str], *, max_rows_per_ticker: int) -> pd.DataFrame:
    con = duckdb.connect(db_path, read_only=True)
    try:
        in_list = "'" + "', '".join(t.replace("'", "") for t in tickers) + "'"
        q = f"""
        WITH ranked AS (
          SELECT ticker, timestamp, close,
                 ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp DESC) AS rn
          FROM quant_core.ohlcv_data
          WHERE ticker IN ({in_list})
        )
        SELECT ticker, timestamp, close
        FROM ranked
        WHERE rn <= {int(max_rows_per_ticker)}
        ORDER BY timestamp ASC
        """
        df = con.execute(q).fetchdf()
    finally:
        con.close()

    if df.empty:
        return df
    wide = df.pivot(index="timestamp", columns="ticker", values="close").sort_index()
    return wide.astype(float)


def equal_weight_daily_returns(close: pd.DataFrame) -> pd.Series:
    rets = close.pct_change().dropna(how="any")
    if rets.shape[1] == 0 or rets.shape[0] < 21:
        return pd.Series(dtype=float)
    ew = rets.mean(axis=1).astype(float)
    ew.name = "ew_portfolio_daily"
    return ew


def json_sanitize(val: Any) -> Any:
    import numpy as _np

    if val is None or isinstance(val, (bool, str)):
        return val
    if isinstance(val, (float, int)) and _np.isfinite(val):
        return float(val)
    if isinstance(val, _np.generic):
        return float(val.item()) if _np.ndim(val) == 0 else str(val)
    if isinstance(val, dict):
        return {str(k): json_sanitize(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [json_sanitize(x) for x in val]
    return str(val)