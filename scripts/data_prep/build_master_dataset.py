#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
import sys

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.data_prep.health_contract import build_health_proxy, load_health_dataset

_DEBUG_LOG_PATH = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-07d446.log"


def _agent_debug_log(hypothesis_id: str, location: str, message: str, data: dict, run_id: str = "baseline") -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": "07d446",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(datetime.now().timestamp() * 1000),
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Construye dataset maestro PM2.5 + salud.")
    parser.add_argument("--start-date", required=True, help="Fecha inicio (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="Fecha fin (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default="data/processed", help="Directorio de salida")
    parser.add_argument("--openaq-file", default="", help="Parquet/CSV OpenAQ")
    parser.add_argument("--siata-file", default="", help="Parquet/CSV SIATA")
    parser.add_argument("--ideam-file", default="", help="Parquet/CSV IDEAM")
    parser.add_argument("--health-file", default="", help="Parquet/CSV de salud (opcional)")
    return parser.parse_args()


def _validate_date(value: str) -> str:
    datetime.strptime(value, "%Y-%m-%d")
    return value


def _load_table(path: str) -> pd.DataFrame:
    if not path:
        return pd.DataFrame()
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {p}")
    if p.suffix.lower() == ".parquet":
        return pd.read_parquet(p)
    return pd.read_csv(p)


def _iqr_filter(df: pd.DataFrame, col: str) -> tuple[pd.DataFrame, int]:
    q1 = df[col].quantile(0.25)
    q3 = df[col].quantile(0.75)
    iqr = q3 - q1
    low = q1 - 1.5 * iqr
    high = q3 + 1.5 * iqr
    mask = (df[col] >= low) & (df[col] <= high)
    removed = int((~mask).sum())
    return df.loc[mask].copy(), removed


def build_master(args: argparse.Namespace) -> tuple[pd.DataFrame, dict]:
    start_date = pd.to_datetime(_validate_date(args.start_date)).date()
    end_date = pd.to_datetime(_validate_date(args.end_date)).date()
    pm_frames = []
    # #region agent log
    _agent_debug_log(
        "H1",
        "build_master_dataset.py:build_master",
        "build_master_input_range",
        {"start_date": str(start_date), "end_date": str(end_date)},
    )
    # #endregion
    for source_name, fp in (("OpenAQ", args.openaq_file), ("SIATA", args.siata_file)):
        df = _load_table(fp)
        if df.empty:
            continue
        required = {"date", "zone", "pm25"}
        missing = required.difference(df.columns)
        if missing:
            raise ValueError(f"{source_name} sin columnas requeridas {sorted(required)}. Faltantes: {sorted(missing)}")
        work = df[["date", "zone", "pm25"]].copy()
        work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.date
        work["zone"] = work["zone"].astype("string").fillna("desconocida")
        work["pm25"] = pd.to_numeric(work["pm25"], errors="coerce")
        pm_frames.append(work.dropna(subset=["date", "pm25"]))
    if not pm_frames:
        raise ValueError("No hay datos PM2.5 para construir dataset maestro.")

    pm = pd.concat(pm_frames, ignore_index=True)
    pm = pm[(pm["date"] >= start_date) & (pm["date"] <= end_date)].copy()
    # #region agent log
    _agent_debug_log(
        "H2",
        "build_master_dataset.py:build_master",
        "pm_after_date_filter",
        {
            "rows": int(len(pm)),
            "min_date": str(pm["date"].min()) if not pm.empty else None,
            "max_date": str(pm["date"].max()) if not pm.empty else None,
        },
    )
    # #endregion
    rows_before = len(pm)
    null_pct_before = float(pm.isna().mean().mean() * 100.0)
    pm = pm.drop_duplicates(subset=["date", "zone", "pm25"])
    rows_after_dedup = len(pm)

    # Imputación por mediana de zona para PM2.5.
    pm["pm25"] = pm["pm25"].fillna(pm.groupby("zone")["pm25"].transform("median"))
    pm["pm25"] = pm["pm25"].fillna(pm["pm25"].median())

    pm, outliers_removed = _iqr_filter(pm, "pm25")
    pm_daily = (
        pm.groupby(["date", "zone"], as_index=False)["pm25"]
        .mean()
        .rename(columns={"pm25": "pm25_daily_mean"})
    )
    pm_daily["year"] = pd.to_datetime(pm_daily["date"]).dt.year
    pm_daily["month"] = pd.to_datetime(pm_daily["date"]).dt.month

    health_df = load_health_dataset(args.health_file)
    used_health_proxy = False
    if health_df.empty:
        health_df = build_health_proxy(pm_daily)
        used_health_proxy = True
    merged = pm_daily.merge(
        health_df[["date", "zone", "resp_cases"] + ([c for c in ["resp_index", "population"] if c in health_df.columns])],
        on=["date", "zone"],
        how="inner",
    )

    ideam = _load_table(args.ideam_file)
    if not ideam.empty and "date" in ideam.columns and "zone" in ideam.columns:
        ideam["date"] = pd.to_datetime(ideam["date"], errors="coerce").dt.date
        ideam["zone"] = ideam["zone"].astype("string")
        keep_cols = [c for c in ["date", "zone", "temperature_c", "humidity_pct", "rain_mm"] if c in ideam.columns]
        merged = merged.merge(ideam[keep_cols], on=["date", "zone"], how="left")

    merged["date"] = pd.to_datetime(merged["date"], errors="coerce").dt.date.astype("string")
    merged = merged.sort_values(["date", "zone"]).reset_index(drop=True)
    # #region agent log
    _agent_debug_log(
        "H3",
        "build_master_dataset.py:build_master",
        "merged_output_date_range",
        {
            "rows": int(len(merged)),
            "min_date": str(pd.to_datetime(merged["date"], errors="coerce").min()) if not merged.empty else None,
            "max_date": str(pd.to_datetime(merged["date"], errors="coerce").max()) if not merged.empty else None,
            "used_health_proxy": bool(used_health_proxy),
        },
    )
    # #endregion

    metadata = {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "rows_before_cleaning": int(rows_before),
        "rows_after_integration": int(len(merged)),
        "variables_count": int(len(merged.columns)),
        "null_pct_before": round(null_pct_before, 3),
        "null_pct_after": round(float(merged.isna().mean().mean() * 100.0), 3),
        "outliers_removed_iqr": int(outliers_removed),
        "duplicates_removed": int(rows_before - rows_after_dedup),
        "coverage_years": sorted(pd.to_datetime(merged["date"]).dt.year.dropna().unique().astype(int).tolist()),
        "join_key": "date+zone",
        "used_health_proxy": used_health_proxy,
    }
    return merged, metadata


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    df, metadata = build_master(args)
    parquet_path = output_dir / "master_2018_2024.parquet"
    json_path = output_dir / "metadata_summary.json"
    df.to_parquet(parquet_path, index=False)
    json_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"rows={len(df)} cols={len(df.columns)} master={parquet_path}")
    print(f"metadata={json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
