#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


HEALTH_COLUMNS = ["date", "zone", "resp_cases", "population"]


def load_health_dataset(path: str | None) -> pd.DataFrame:
    """
    Contrato esperado:
      - date (YYYY-MM-DD)
      - zone
      - resp_cases (numérico)
      - population (opcional)
    """
    if not path:
        return pd.DataFrame(columns=HEALTH_COLUMNS)
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Health dataset no existe: {file_path}")
    if file_path.suffix.lower() == ".parquet":
        df = pd.read_parquet(file_path)
    else:
        df = pd.read_csv(file_path)

    lower_map = {c.lower().strip(): c for c in df.columns}
    date_col = lower_map.get("date") or lower_map.get("fecha")
    zone_col = lower_map.get("zone") or lower_map.get("zona") or lower_map.get("municipio")
    cases_col = lower_map.get("resp_cases") or lower_map.get("cases") or lower_map.get("enfermedades_respiratorias")
    pop_col = lower_map.get("population") or lower_map.get("poblacion")

    if not date_col or not zone_col or not cases_col:
        raise ValueError(
            "Dataset de salud inválido. Requiere columnas equivalentes a: date, zone, resp_cases. "
            f"Columnas recibidas: {list(df.columns)}"
        )
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df[date_col], errors="coerce").dt.date.astype("string"),
            "zone": df[zone_col].astype("string"),
            "resp_cases": pd.to_numeric(df[cases_col], errors="coerce"),
            "population": pd.to_numeric(df[pop_col], errors="coerce") if pop_col else np.nan,
        }
    )
    return out.dropna(subset=["date", "zone", "resp_cases"])


def build_health_proxy(pm25_daily: pd.DataFrame) -> pd.DataFrame:
    """
    Fallback temporal mientras llega fuente oficial:
    - resp_index: escala 0-100 por umbral OMS + persistencia de PM2.5.
    - resp_cases: aproximación para visualización (no clínica).
    """
    work = pm25_daily.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.sort_values(["zone", "date"])
    pm25 = pd.to_numeric(work["pm25_daily_mean"], errors="coerce").fillna(0)
    rolling = pm25.rolling(window=7, min_periods=1).mean()
    excess = (pm25 - 15).clip(lower=0)  # referencia OMS diaria 15 ug/m3
    score = (0.65 * excess + 0.35 * (rolling - 15).clip(lower=0)).clip(lower=0)
    max_score = float(score.max()) if float(score.max()) > 0 else 1.0
    resp_index = (100.0 * score / max_score).clip(0, 100)
    work["resp_index"] = resp_index
    work["resp_cases"] = (2 + np.round(resp_index / 8.0)).astype(int)
    return work[["date", "zone", "resp_cases", "resp_index"]].assign(date=lambda d: d["date"].dt.date)
