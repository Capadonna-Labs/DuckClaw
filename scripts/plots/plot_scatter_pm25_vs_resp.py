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
    parser = argparse.ArgumentParser(description="Scatter PM2.5 vs enfermedades respiratorias.")
    parser.add_argument("--start-date", required=True, help="Fecha inicio (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="Fecha fin (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default="reports/figures", help="Directorio de salida")
    parser.add_argument("--master-file", default="data/processed/master_2018_2024.parquet")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(args.master_file) if args.master_file.endswith(".parquet") else pd.read_csv(args.master_file)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    mask = (df["date"] >= pd.to_datetime(args.start_date)) & (df["date"] <= pd.to_datetime(args.end_date))
    work = df.loc[mask].dropna(subset=["pm25_daily_mean", "resp_cases"]).copy()

    pearson = float(work["pm25_daily_mean"].corr(work["resp_cases"], method="pearson"))
    spearman = float(work["pm25_daily_mean"].corr(work["resp_cases"], method="spearman"))

    plt.figure(figsize=(10, 6))
    sns.regplot(
        data=work,
        x="pm25_daily_mean",
        y="resp_cases",
        scatter_kws={"alpha": 0.45, "s": 24},
        line_kws={"color": "red"},
    )
    title = f"Relación PM2.5 vs enfermedades respiratorias ({args.start_date} a {args.end_date})"
    plt.title(title)
    plt.xlabel("PM2.5 diario promedio (ug/m3)")
    plt.ylabel("Casos respiratorios (real/proxy)")
    plt.grid(alpha=0.2)
    plt.text(
        0.01,
        0.98,
        f"Pearson: {pearson:.3f}\nSpearman: {spearman:.3f}",
        transform=plt.gca().transAxes,
        va="top",
        ha="left",
        bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "gray"},
    )
    png = out_dir / "scatter_pm25_vs_resp.png"
    svg = out_dir / "scatter_pm25_vs_resp.svg"
    plt.tight_layout()
    plt.savefig(png, dpi=180)
    plt.savefig(svg)
    print(f"figure={png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
