#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

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
    # #region agent log
    _agent_debug_log(
        "H4",
        "plot_scatter_pm25_vs_resp.py:main",
        "scatter_input_args",
        {
            "start_date_arg": args.start_date,
            "end_date_arg": args.end_date,
            "master_file": args.master_file,
            "df_rows": int(len(df)),
        },
    )
    # #endregion
    mask = (df["date"] >= pd.to_datetime(args.start_date)) & (df["date"] <= pd.to_datetime(args.end_date))
    work = df.loc[mask].dropna(subset=["pm25_daily_mean", "resp_cases"]).copy()
    # #region agent log
    _agent_debug_log(
        "H4",
        "plot_scatter_pm25_vs_resp.py:main",
        "scatter_work_range",
        {
            "work_rows": int(len(work)),
            "work_min_date": str(work["date"].min()) if not work.empty else None,
            "work_max_date": str(work["date"].max()) if not work.empty else None,
        },
    )
    # #endregion

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
    # #region agent log
    _agent_debug_log(
        "H5",
        "plot_scatter_pm25_vs_resp.py:main",
        "scatter_title_rendered",
        {"title": title},
    )
    # #endregion
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
