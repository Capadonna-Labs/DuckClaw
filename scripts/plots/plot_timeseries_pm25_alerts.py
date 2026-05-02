#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serie temporal PM2.5 con periodos críticos.")
    parser.add_argument("--start-date", required=True, help="Fecha inicio (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="Fecha fin (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default="reports/figures", help="Directorio de salida")
    parser.add_argument("--master-file", default="data/processed/master_2018_2024.parquet")
    parser.add_argument("--threshold", type=float, default=15.0, help="Umbral OMS diario PM2.5")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(args.master_file) if args.master_file.endswith(".parquet") else pd.read_csv(args.master_file)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    mask = (df["date"] >= pd.to_datetime(args.start_date)) & (df["date"] <= pd.to_datetime(args.end_date))
    work = df.loc[mask].copy()
    ts = (
        work.groupby("date", as_index=False)["pm25_daily_mean"]
        .mean()
        .sort_values("date")
        .rename(columns={"pm25_daily_mean": "pm25"})
    )
    ts["critical"] = ts["pm25"] > float(args.threshold)

    plt.figure(figsize=(12, 6))
    plt.plot(ts["date"], ts["pm25"], color="#1f77b4", linewidth=1.5, label="PM2.5 diario")
    plt.axhline(args.threshold, color="red", linestyle="--", linewidth=1.2, label=f"Umbral {args.threshold} ug/m3")

    critical = ts[ts["critical"]]
    if not critical.empty:
        plt.fill_between(
            critical["date"],
            critical["pm25"],
            args.threshold,
            where=critical["pm25"] >= args.threshold,
            color="orange",
            alpha=0.25,
            label="Periodos críticos",
        )

    plt.title("Evolución temporal de PM2.5 y periodos críticos")
    plt.xlabel("Fecha")
    plt.ylabel("PM2.5 diario promedio (ug/m3)")
    plt.grid(alpha=0.2)
    plt.legend()
    ax = plt.gca()
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.xticks(rotation=35, ha="right")
    plt.tight_layout()

    png = out_dir / "timeseries_pm25_alerts.png"
    svg = out_dir / "timeseries_pm25_alerts.svg"
    plt.savefig(png, dpi=180)
    plt.savefig(svg)
    print(f"figure={png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
