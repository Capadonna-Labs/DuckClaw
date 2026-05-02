#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Boxplot de PM2.5 por zona.")
    parser.add_argument("--start-date", required=True, help="Fecha inicio (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="Fecha fin (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default="reports/figures", help="Directorio de salida")
    parser.add_argument("--master-file", default="data/processed/master_2018_2024.parquet")
    parser.add_argument("--top-n", type=int, default=10, help="Número de zonas a mostrar")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(args.master_file) if args.master_file.endswith(".parquet") else pd.read_csv(args.master_file)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    mask = (df["date"] >= pd.to_datetime(args.start_date)) & (df["date"] <= pd.to_datetime(args.end_date))
    work = df.loc[mask].dropna(subset=["zone", "pm25_daily_mean"]).copy()

    ranking = (
        work.groupby("zone", as_index=False)["pm25_daily_mean"]
        .mean()
        .sort_values("pm25_daily_mean", ascending=False)
        .head(args.top_n)
    )
    top_zones = ranking["zone"].tolist()
    plot_df = work[work["zone"].isin(top_zones)].copy()

    plt.figure(figsize=(12, 6))
    sns.boxplot(data=plot_df, x="zone", y="pm25_daily_mean", order=top_zones)
    plt.title("Distribución PM2.5 por zonas de mayor riesgo")
    plt.xlabel("Zona")
    plt.ylabel("PM2.5 diario promedio (ug/m3)")
    plt.xticks(rotation=30, ha="right")
    plt.grid(axis="y", alpha=0.2)
    plt.tight_layout()

    png = out_dir / "boxplot_pm25_by_zone.png"
    svg = out_dir / "boxplot_pm25_by_zone.svg"
    plt.savefig(png, dpi=180)
    plt.savefig(svg)
    print(f"figure={png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
