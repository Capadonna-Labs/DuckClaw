#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

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
    # #region agent log
    _agent_debug_log(
        "H4",
        "plot_timeseries_pm25_alerts.py:main",
        "timeseries_input_args",
        {
            "start_date_arg": args.start_date,
            "end_date_arg": args.end_date,
            "master_file": args.master_file,
            "df_rows": int(len(df)),
        },
    )
    # #endregion
    mask = (df["date"] >= pd.to_datetime(args.start_date)) & (df["date"] <= pd.to_datetime(args.end_date))
    work = df.loc[mask].copy()
    ts = (
        work.groupby("date", as_index=False)["pm25_daily_mean"]
        .mean()
        .sort_values("date")
        .rename(columns={"pm25_daily_mean": "pm25"})
    )
    # #region agent log
    _agent_debug_log(
        "H3",
        "plot_timeseries_pm25_alerts.py:main",
        "timeseries_grouped_range",
        {
            "rows": int(len(ts)),
            "min_date": str(ts["date"].min()) if not ts.empty else None,
            "max_date": str(ts["date"].max()) if not ts.empty else None,
        },
    )
    # #endregion
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
    # #region agent log
    labels = [t.get_text() for t in ax.get_xticklabels()]
    _agent_debug_log(
        "H5",
        "plot_timeseries_pm25_alerts.py:main",
        "timeseries_xtick_labels",
        {"labels": labels[:10], "label_count": len(labels)},
    )
    # #endregion
    plt.tight_layout()

    png = out_dir / "timeseries_pm25_alerts.png"
    svg = out_dir / "timeseries_pm25_alerts.svg"
    plt.savefig(png, dpi=180)
    plt.savefig(svg)
    print(f"figure={png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
