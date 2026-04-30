import streamlit as st
import plotly.graph_objects as go
import duckdb
import pandas as pd
import numpy as np
import os
import sys
import json
import math
import statistics
from pathlib import Path
from dotenv import load_dotenv
import time
from datetime import datetime

# 1. Configuración de Entorno
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from packages.agents.src.duckclaw.forge.skills.ibkr_bridge import (
    fetch_ibkr_total_equity_numeric, 
    fetch_ibkr_unrealized_pnl_total_numeric,
    _get_ibkr_portfolio_impl
)


def _debug_log_dashboard(
    *,
    hypothesis_id: str,
    message: str,
    data: dict,
    run_id: str = "cfd_dashboard_launch_v1",
) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": "c964f7",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": "scripts/humans/cfd_dashboard.py",
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(
            "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
            "a",
            encoding="utf-8",
        ) as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # endregion


def _resolve_quant_db_path() -> str | None:
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        os.environ.get("DUCKCLAW_QUANT_SCRIPT_DB"),
        os.environ.get("DUCKCLAW_QUANT_TRADER_DB_PATH"),
    ]
    for raw in candidates:
        p = str(raw or "").strip()
        if not p:
            continue
        candidate = Path(p)
        if not candidate.is_absolute():
            candidate = (repo_root / candidate).resolve()
        if candidate.exists():
            _debug_log_dashboard(
                hypothesis_id="H_db_path_resolution",
                message="db_path_resolved_from_env",
                data={"source_tail": p[-120:], "resolved_tail": str(candidate)[-180:]},
            )
            return str(candidate)
    discovered = sorted(repo_root.glob("db/private/*/quant_traderdb1.duckdb"), reverse=True)
    if discovered:
        picked = str(discovered[0].resolve())
        _debug_log_dashboard(
            hypothesis_id="H_db_path_resolution",
            message="db_path_resolved_by_glob",
            data={"resolved_tail": picked[-180:], "candidates_count": len(discovered)},
        )
        return picked
    _debug_log_dashboard(
        hypothesis_id="H_db_path_resolution",
        message="db_path_resolution_failed",
        data={
            "has_quant_script_db": bool((os.environ.get("DUCKCLAW_QUANT_SCRIPT_DB") or "").strip()),
            "has_quant_trader_db_path": bool((os.environ.get("DUCKCLAW_QUANT_TRADER_DB_PATH") or "").strip()),
        },
    )
    return None


st.set_page_config(page_title="DuckClaw CFD Command Center", layout="wide", page_icon="🦆")

# Estilo Dark Aeroespacial
st.markdown("""
    <style>
    .main { background-color: #0f172a; color: #f8f9fa; }
    .stMetric { background-color: #1e293b; padding: 15px; border-radius: 10px; border: 1px solid #334155; }
    [data-testid="stMetricValue"] { font-size: 26px; color: #ef4444; }
    </style>
    """, unsafe_allow_html=True)

def get_db_data():
    db_path = _resolve_quant_db_path()
    if not db_path:
        raise RuntimeError(
            "No encontré DB de Quant. Configura DUCKCLAW_QUANT_SCRIPT_DB o DUCKCLAW_QUANT_TRADER_DB_PATH en .env."
        )
    con = duckdb.connect(db_path, read_only=True)
    
    session = con.execute("SELECT anchor_equity, session_uid FROM quant_core.trading_sessions WHERE id = 'active' AND status = 'ACTIVE'").df()
    fluid_state = con.execute("SELECT * FROM quant_core.fluid_state ORDER BY timestamp ASC").df()
    signals = con.execute("SELECT * FROM quant_core.trade_signals ORDER BY updated_at DESC LIMIT 20").df()
    config_all = con.execute("SELECT key, value FROM agent_config").df()
    
    con.close()
    return fluid_state, signals, session, config_all

def _safe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _dedupe_snapshots(snaps: list[float]) -> list[float]:
    out: list[float] = []
    eps = 1e-4
    for v in snaps:
        if not out or abs(float(v) - float(out[-1])) > eps:
            out.append(float(v))
    return out


def _compute_tick_tearsheet_metrics_from_pnl(*, snapshots: list[float], anchor_equity: float) -> dict[str, float | None]:
    # Espejo de /trading_session --status
    out: dict[str, float | None] = {
        "sharpe": None,
        "sortino": None,
        "volatility_pct": None,
        "max_drawdown_pct": None,
    }
    if anchor_equity <= 0 or not isinstance(snapshots, list) or len(snapshots) < 3:
        return out
    try:
        pnl_series = [float(x) for x in snapshots]
    except (TypeError, ValueError):
        return out
    equity = [anchor_equity + p for p in pnl_series]
    if len(equity) < 3:
        return out
    rets: list[float] = []
    for i in range(1, len(equity)):
        prev = float(equity[i - 1])
        curr = float(equity[i])
        if prev <= 0:
            continue
        rets.append((curr / prev) - 1.0)
    if len(rets) < 2:
        return out
    mean_r = statistics.fmean(rets)
    std_r = statistics.pstdev(rets)
    if std_r > 1e-12:
        out["sharpe"] = (mean_r / std_r) * math.sqrt(252.0)
        out["volatility_pct"] = std_r * math.sqrt(252.0) * 100.0
    downside = [r for r in rets if r < 0]
    if downside:
        down_std = statistics.pstdev(downside)
        if down_std > 1e-12:
            out["sortino"] = (mean_r / down_std) * math.sqrt(252.0)
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (v / peak) - 1.0
            if dd < max_dd:
                max_dd = dd
    out["max_drawdown_pct"] = max_dd * 100.0
    return out


def _extract_snapshots_from_config(config_df: pd.DataFrame, active_uid: str) -> tuple[list[float], str]:
    if config_df.empty:
        _debug_log_dashboard(
            hypothesis_id="H_snapshot_source_mismatch",
            message="snapshot_extract_empty_config",
            data={"active_uid_tail": str(active_uid)[-12:]},
        )
        return [], "fallback"
    try:
        uid_rows = config_df[
            config_df["key"].astype(str).str.endswith("trading_session_pnl_hist_uid")
            & (config_df["value"].astype(str) == str(active_uid))
        ]
        if uid_rows.empty:
            _debug_log_dashboard(
                hypothesis_id="H_snapshot_source_mismatch",
                message="snapshot_extract_no_uid_match",
                data={
                    "active_uid_tail": str(active_uid)[-12:],
                    "hist_uid_rows_total": int(
                        config_df["key"].astype(str).str.endswith("trading_session_pnl_hist_uid").sum()
                    ),
                },
            )
            return [], "fallback"
        chat_prefixes = [
            str(k).replace("trading_session_pnl_hist_uid", "") for k in uid_rows["key"].tolist()
        ]
        chat_prefix = str(chat_prefixes[-1] if chat_prefixes else "")
        key = f"{chat_prefix}trading_session_pnl_snapshots_json"
        snap_rows = config_df[config_df["key"] == key]
        if snap_rows.empty:
            _debug_log_dashboard(
                hypothesis_id="H_snapshot_source_mismatch",
                message="snapshot_extract_missing_snap_key",
                data={"active_uid_tail": str(active_uid)[-12:], "chat_prefix_tail": chat_prefix[-16:]},
            )
            return [], "fallback"
        snapshots = json.loads(str(snap_rows["value"].values[0]))
        if not isinstance(snapshots, list):
            return [], "fallback"
        clean = [float(x) for x in snapshots]
        deduped = _dedupe_snapshots(clean)
        _debug_log_dashboard(
            hypothesis_id="H_snapshot_source_mismatch",
            message="snapshot_extract_selected_series",
            data={
                "active_uid_tail": str(active_uid)[-12:],
                "chat_prefix_tail": chat_prefix[-16:],
                "candidate_prefix_count": len(chat_prefixes),
                "raw_len": len(clean),
                "deduped_len": len(deduped),
                "last_raw": None if not clean else round(float(clean[-1]), 4),
            },
        )
        return deduped, "snapshot"
    except Exception:
        return [], "fallback"


def load_db_context() -> dict:
    fluid, signals, session, config_df = get_db_data()
    return {"fluid": fluid, "signals": signals, "session": session, "config_df": config_df}


def load_live_context() -> dict:
    live_equity, _ = fetch_ibkr_total_equity_numeric()
    live_unrealized, _ = fetch_ibkr_unrealized_pnl_total_numeric()
    portfolio_text = _get_ibkr_portfolio_impl()
    return {"live_equity": live_equity, "live_unrealized": live_unrealized, "portfolio_text": portfolio_text}


def build_reconciled_pnl_series(
    *,
    config_df: pd.DataFrame,
    session_uid: str,
    anchor_equity: float,
    live_equity: float | None,
    live_unrealized: float | None,
) -> tuple[list[float], dict]:
    snapshots, source = _extract_snapshots_from_config(config_df, session_uid)
    live_equity_f = _safe_float(live_equity)
    live_unrealized_f = _safe_float(live_unrealized)
    # Espejo de /trading_session --status: PnL actual viene de la lógica de pnl_now
    # (normalmente equivalente al unrealized live), no de equity-anchor.
    pnl_live_now = live_unrealized_f
    pnl_equity_delta = (live_equity_f - anchor_equity) if (live_equity_f is not None and anchor_equity > 0) else None
    pnl_for_series = pnl_live_now if pnl_live_now is not None else pnl_equity_delta
    source_tag = "live_pnl_now" if pnl_live_now is not None else ("equity_delta_fallback" if pnl_equity_delta is not None else source)
    if not snapshots:
        if pnl_for_series is not None:
            return [float(pnl_for_series)], {"series_source": source_tag, "pnl_live_now": pnl_live_now, "pnl_equity_delta": pnl_equity_delta}
        return [0.0], {"series_source": "fallback_zero", "pnl_live_now": None, "pnl_equity_delta": None}
    if pnl_for_series is not None:
        snapshots[-1] = float(pnl_for_series)
    return snapshots[-64:], {"series_source": source_tag if pnl_for_series is not None else source, "pnl_live_now": pnl_live_now, "pnl_equity_delta": pnl_equity_delta}


def _fmt_money(v: float | None) -> str:
    return f"${v:,.2f}" if v is not None else "N/D"


def _fmt_pct(v: float | None) -> str:
    return f"{v:.2f}%" if v is not None else "N/D"

def build_pnl_curve(pnl_history):
    if not pnl_history:
        return go.Figure().update_layout(template="plotly_dark", title="Esperando datos...")
    
    steps = list(range(len(pnl_history)))
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=steps, y=pnl_history, mode='lines', name='PnL ($)',
        line=dict(color='#60a5fa', width=2), fill='tozeroy', fillcolor='rgba(96, 165, 250, 0.1)'
    ))
    
    fig.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.3)
    
    fig.update_layout(
        height=300, margin=dict(l=0, r=0, t=20, b=0),
        xaxis=dict(title="Paso (Tick)", showgrid=True, gridcolor='rgba(148, 163, 184, 0.1)'),
        yaxis=dict(title="PnL ($)", showgrid=True, gridcolor='rgba(148, 163, 184, 0.1)'),
        paper_bgcolor='rgba(15, 23, 42, 0.5)', plot_bgcolor='rgba(30, 41, 59, 0.3)',
        template="plotly_dark", hovermode='x unified'
    )
    return fig

_PHASE_COLORS = {"GAS": "#22c55e", "PLASMA": "#ef4444", "SOLID": "#3b82f6", "LIQUID": "#f59e0b"}
_PHASE_ZONE_COLORS = {"SOLID": "#1a237e", "LIQUID": "#1b5e20", "GAS": "#e65100", "PLASMA": "#b71c1c"}
_ASSET_COLORS = {"META": "#ef4444", "SPY": "#3b82f6"}


def _phase_from_temp(temp: float | None) -> str:
    t = _safe_float(temp)
    if t is None:
        return "UNKNOWN"
    if t < 0.010:
        return "SOLID"
    if t < 0.020:
        return "LIQUID"
    if t < 0.035:
        return "GAS"
    return "PLASMA"


def _phase_z(phase: str) -> float:
    return {"PLASMA": -1.0, "LIQUID": 0.0, "SOLID": 1.0, "GAS": 2.0}.get(str(phase).upper(), 0.0)


def _asset_color(ticker: str) -> str:
    return _ASSET_COLORS.get(str(ticker).upper(), "#94a3b8")


def _prepare_radar_dataset(df: pd.DataFrame, selected_tickers: list[str]) -> tuple[pd.DataFrame, list, float, float]:
    if df.empty or not selected_tickers:
        return pd.DataFrame(), [], 0.0, 1.0
    df_plot = df[df["ticker"].isin(selected_tickers)].copy().sort_values("timestamp")
    all_ts = df_plot["timestamp"].unique()
    if len(all_ts) == 0:
        return pd.DataFrame(), [], 0.0, 1.0
    grid = pd.MultiIndex.from_product([all_ts, selected_tickers], names=["timestamp", "ticker"])
    df_plot = df_plot.set_index(["timestamp", "ticker"]).reindex(grid).reset_index()
    # Mantener huella de datos parciales antes de rellenar para visualización.
    df_plot["raw_mass"] = pd.to_numeric(df_plot.get("mass"), errors="coerce")
    df_plot["raw_temperature"] = pd.to_numeric(df_plot.get("temperature"), errors="coerce")
    df_plot["is_partial"] = df_plot["raw_mass"].isna() | df_plot["raw_temperature"].isna()
    cols_to_fill = ["mass", "temperature", "phase", "volume", "close"]
    for c in cols_to_fill:
        if c not in df_plot.columns:
            df_plot[c] = np.nan
    df_plot[cols_to_fill] = df_plot.groupby("ticker")[cols_to_fill].ffill().bfill()
    df_plot["mass"] = pd.to_numeric(df_plot["mass"], errors="coerce")
    df_plot["temperature"] = pd.to_numeric(df_plot["temperature"], errors="coerce")
    df_plot["volume"] = pd.to_numeric(df_plot["volume"], errors="coerce")
    df_plot["close"] = pd.to_numeric(df_plot["close"], errors="coerce")
    # Masa log10(close*vol) según spec.
    df_plot["mass_calc"] = np.where(
        (df_plot["close"] > 0) & (df_plot["volume"] > 0),
        np.log10(df_plot["close"] * df_plot["volume"]),
        np.nan,
    )
    if df_plot["mass_calc"].isna().all():
        df_plot["mass_calc"] = np.log10(np.clip(df_plot["mass"].abs(), 1e-9, None))
    fallback_x = float(np.nanmedian(df_plot["mass_calc"])) if not df_plot["mass_calc"].isna().all() else 0.0
    df_plot["x"] = df_plot["mass_calc"].fillna(fallback_x)
    df_plot["y"] = df_plot["temperature"].fillna(0.0)
    df_plot["phase"] = df_plot["y"].apply(_phase_from_temp)
    df_plot["z"] = df_plot["phase"].apply(_phase_z)
    max_vol = float(np.nanmax(df_plot["volume"])) if not df_plot["volume"].isna().all() else 1.0
    max_vol = max(max_vol, 1.0)
    size_raw = (df_plot["volume"].fillna(0.0) / max_vol) * 40.0 + 10.0
    df_plot["display_size"] = np.clip(size_raw, 10.0, 50.0)
    df_plot["asset_color"] = df_plot["ticker"].apply(_asset_color)
    df_plot["ts_str"] = df_plot["timestamp"].astype(str)
    x_mid = float(np.nanmedian(df_plot["x"])) if not df_plot["x"].isna().all() else 0.0
    x_range = float(np.nanmax(df_plot["x"]) - np.nanmin(df_plot["x"])) if not df_plot["x"].isna().all() else 1.0
    return df_plot, list(all_ts), x_mid, max(1e-6, x_range)


def _frame_state_for_idx(df_plot: pd.DataFrame, all_ts: list, frame_idx: int) -> pd.DataFrame:
    if df_plot.empty or not all_ts:
        return pd.DataFrame()
    frame_idx = max(0, min(int(frame_idx), max(0, len(all_ts) - 1)))
    ts_value = all_ts[frame_idx]
    df_frame = df_plot[df_plot["timestamp"] == ts_value].copy()
    # region agent log
    _debug_log_dashboard(
        hypothesis_id="H_radar_legend_sync",
        message="radar_frame_selected",
        data={
            "frame_idx": frame_idx,
            "ts": str(ts_value),
            "tickers": [str(x) for x in df_frame["ticker"].tolist()],
            "phases": [str(x) for x in df_frame["phase"].tolist()],
        },
    )
    # endregion
    return df_frame


def _build_surface(df_plot: pd.DataFrame, x_mid: float, x_range: float) -> go.Surface:
    x_min = float(np.nanmin(df_plot["x"])) if not df_plot["x"].isna().all() else (x_mid - 1.0)
    x_max = float(np.nanmax(df_plot["x"])) if not df_plot["x"].isna().all() else (x_mid + 1.0)
    mass_range = np.linspace(x_min, x_max, 30)
    temp_range = np.linspace(0.0, 0.05, 30)
    xg, yg = np.meshgrid(mass_range, temp_range)
    zg = (
        2.0 * ((yg - 0.015) ** 2) / (0.015**2) +
        0.3 * ((xg - x_mid) ** 2) / (max(x_range, 1e-6) ** 2)
    ) * -0.3
    return go.Surface(
        x=xg,
        y=yg,
        z=zg,
        colorscale=[
            [0.0, "#1a237e"],
            [0.25, "#1b5e20"],
            [0.6, "#bf360c"],
            [1.0, "#b71c1c"],
        ],
        opacity=0.25,
        showscale=False,
        hoverinfo="skip",
        lighting=dict(ambient=0.8, diffuse=0.5, roughness=0.5, specular=0.2),
        name="surface",
        showlegend=False,
    )


def _build_threshold_lines(x_min: float, x_max: float) -> list[go.Scatter3d]:
    lines: list[go.Scatter3d] = []
    for val, label in [(0.010, "0.010"), (0.020, "0.020"), (0.035, "0.035")]:
        lines.append(
            go.Scatter3d(
                x=[x_min, x_max],
                y=[val, val],
                z=[0.001, 0.001],
                mode="lines+text",
                text=["", label],
                textposition="top right",
                line=dict(color="rgba(255,255,255,0.65)", width=2, dash="dash"),
                hoverinfo="skip",
                showlegend=False,
            )
        )
    return lines


def _build_zone_labels(x_mid: float) -> list[go.Scatter3d]:
    zones = [
        ("SOLID", x_mid, 0.005, "#3949ab"),
        ("LIQUID", x_mid, 0.015, "#2e7d32"),
        ("GAS", x_mid, 0.027, "#bf360c"),
        ("PLASMA", x_mid, 0.042, "#c62828"),
    ]
    out: list[go.Scatter3d] = []
    for name, x, y, color in zones:
        out.append(
            go.Scatter3d(
                x=[x], y=[y], z=[-0.25],
                mode="text",
                text=[name],
                textfont=dict(color=color, size=13, family="monospace"),
                hoverinfo="skip",
                showlegend=False,
            )
        )
    return out


def _frame_traces(df_plot: pd.DataFrame, all_ts: list, idx: int, show_thresholds: bool) -> list:
    ts_value = all_ts[idx]
    frame = df_plot[df_plot["timestamp"] == ts_value].copy()
    traces: list = []
    x_min = float(np.nanmin(df_plot["x"])) if not df_plot["x"].isna().all() else -1.0
    x_max = float(np.nanmax(df_plot["x"])) if not df_plot["x"].isna().all() else 1.0
    if show_thresholds:
        traces.extend(_build_threshold_lines(x_min, x_max))
    for _, row in frame.iterrows():
        ticker = str(row["ticker"])
        color = str(row["asset_color"])
        hist = df_plot[(df_plot["ticker"] == ticker) & (df_plot["timestamp"] <= ts_value)].sort_values("timestamp").tail(6)
        if len(hist) > 1:
            opacities = [0.1, 0.2, 0.4, 0.6, 0.8, 1.0][-len(hist):]
            trail_colors = [f"rgba(255,255,255,{o})" if i < len(hist)-1 else color for i, o in enumerate(opacities)]
            traces.append(
                go.Scatter3d(
                    x=hist["x"].tolist(),
                    y=hist["y"].tolist(),
                    z=[0.01] * len(hist),
                    mode="lines+markers",
                    line=dict(color=color, width=4, dash="dot"),
                    marker=dict(size=[4, 5, 6, 7, 8, 10][-len(hist):], color=trail_colors, symbol="circle"),
                    name=f"{ticker} trail",
                    showlegend=False,
                    hoverinfo="skip",
                )
            )
        phase = str(row["phase"]).upper()
        partial = bool(row.get("is_partial", False))
        hover = (
            f"<b>{ticker}</b><br>"
            f"Timestamp: {row['ts_str']}<br>"
            f"Masa: {10 ** float(row['x']):.2e}<br>"
            f"Temperatura: {float(row['y']):.4f} ({float(row['y'])*100:.2f}%)<br>"
            f"Fase: {phase}<br>"
            f"Volumen: {float(row['volume']) if not pd.isna(row['volume']) else 0:,.0f}"
        )
        if partial:
            hover += "<br><b>Datos parciales — tool call incompleto en este tick</b>"
        traces.append(
            go.Scatter3d(
                x=[row["x"]], y=[row["y"]], z=[0.02],
                mode="markers",
                marker=dict(size=min(60, float(row["display_size"]) + 12), color="rgba(255,255,255,0.1)", symbol="circle"),
                hoverinfo="skip",
                showlegend=False,
            )
        )
        traces.append(
            go.Scatter3d(
                x=[row["x"]], y=[row["y"]], z=[0.02],
                mode="markers+text",
                marker=dict(
                    size=float(row["display_size"]),
                    color=color,
                    symbol="circle",
                    line=dict(
                        color="red" if partial else "white",
                        width=2,
                    ),
                ),
                text=[ticker],
                textposition="top center",
                textfont=dict(color="white", size=11),
                name=f"{ticker} (actual)",
                hovertemplate=hover + "<extra></extra>",
                showlegend=True,
            )
        )
    traces.extend(_build_zone_labels(float((x_min + x_max) / 2.0)))
    return traces


def build_animated_radar_3d(
    df_plot: pd.DataFrame,
    *,
    frame_idx: int,
    show_thresholds: bool,
    camera: dict,
    x_mid: float,
    x_range: float,
) -> go.Figure:
    if df_plot.empty:
        return go.Figure()
    all_ts = sorted(df_plot["timestamp"].unique().tolist())
    frame_idx = max(0, min(int(frame_idx), max(0, len(all_ts) - 1)))
    surface = _build_surface(df_plot, x_mid=x_mid, x_range=x_range)
    initial_traces = _frame_traces(df_plot, all_ts, frame_idx, show_thresholds=show_thresholds)
    fig = go.Figure(data=[surface] + initial_traces)
    frames = []
    for i, ts in enumerate(all_ts):
        fr_traces = [surface] + _frame_traces(df_plot, all_ts, i, show_thresholds=show_thresholds)
        frames.append(go.Frame(name=str(ts), data=fr_traces))
    fig.frames = frames
    x_min = float(np.nanmin(df_plot["x"])) if not df_plot["x"].isna().all() else -1.0
    x_max = float(np.nanmax(df_plot["x"])) if not df_plot["x"].isna().all() else 1.0
    fig.update_layout(
        height=520,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(10,10,10,1)",
        plot_bgcolor="rgba(10,10,10,1)",
        font=dict(color="white"),
        scene=dict(
            camera=camera,
            xaxis=dict(
                title="Masa (log10 close×vol)",
                range=[x_min - 0.1, x_max + 0.1],
                showgrid=True,
                gridcolor="rgba(255,255,255,0.1)",
                backgroundcolor="rgba(0,0,0,0)",
                color="white",
            ),
            yaxis=dict(
                title="Temperatura (σ retornos)",
                range=[0, 0.055],
                showgrid=True,
                gridcolor="rgba(255,255,255,0.1)",
                backgroundcolor="rgba(0,0,0,0)",
                color="white",
            ),
            zaxis=dict(showticklabels=False, showgrid=False, zeroline=False, title="", range=[-0.4, 0.1]),
            bgcolor="rgba(10,10,10,1)",
            aspectmode="manual",
            aspectratio=dict(x=1.8, y=1.2, z=0.4),
        ),
        legend=dict(
            bgcolor="rgba(20,20,20,0.8)",
            bordercolor="rgba(255,255,255,0.2)",
            borderwidth=1,
            font=dict(color="white"),
        ),
        updatemenus=[
            dict(
                type="buttons",
                showactive=False,
                x=0.02,
                y=1.02,
                xanchor="left",
                yanchor="bottom",
                buttons=[
                    dict(label="▶", method="animate", args=[None, {"frame": {"duration": 200, "redraw": True}, "transition": {"duration": 200}, "fromcurrent": True}]),
                    dict(label="■", method="animate", args=[[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}]),
                ],
            )
        ],
        sliders=[
            dict(
                active=frame_idx,
                pad={"t": 35},
                steps=[{"label": str(ts), "method": "animate", "args": [[str(ts)], {"mode": "immediate", "frame": {"duration": 0, "redraw": True}, "transition": {"duration": 0}}]} for ts in all_ts],
            )
        ],
    )
    return fig

def main():
    script_ctx_present = False
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        script_ctx_present = get_script_run_ctx() is not None
    except Exception:
        script_ctx_present = False
    _debug_log_dashboard(
        hypothesis_id="H_streamlit_bare_mode",
        message="main_entry",
        data={
            "script_ctx_present": bool(script_ctx_present),
            "argv": [str(x) for x in sys.argv[:4]],
        },
    )
    st.sidebar.title("Operacion Manual")
    if st.sidebar.button("Refrescar Telemetria", width="stretch"):
        st.rerun()
    st.sidebar.markdown("### Vista CFD")
    if "cfd_eye_x" not in st.session_state:
        st.session_state["cfd_eye_x"] = 1.5
    if "cfd_eye_y" not in st.session_state:
        st.session_state["cfd_eye_y"] = -1.8
    if "cfd_eye_z" not in st.session_state:
        st.session_state["cfd_eye_z"] = 0.8
    if "cfd_kinetic" not in st.session_state:
        st.session_state["cfd_kinetic"] = False
    if "cfd_angulo" not in st.session_state:
        st.session_state["cfd_angulo"] = 0.0
    st.session_state["cfd_eye_x"] = st.sidebar.slider("Rotación X", 0.5, 2.5, float(st.session_state["cfd_eye_x"]), 0.1)
    st.session_state["cfd_eye_y"] = st.sidebar.slider("Rotación Y", -2.5, -0.5, float(st.session_state["cfd_eye_y"]), 0.1)
    st.session_state["cfd_eye_z"] = st.sidebar.slider("Altura", 0.3, 1.5, float(st.session_state["cfd_eye_z"]), 0.1)
    st.session_state["cfd_kinetic"] = st.sidebar.toggle("Modo cinético", value=bool(st.session_state["cfd_kinetic"]))
    if st.session_state["cfd_kinetic"]:
        if st.sidebar.button("STOP modo cinético", width="stretch", type="primary"):
            st.session_state["cfd_kinetic"] = False
        else:
            st.session_state["cfd_angulo"] = float(st.session_state.get("cfd_angulo", 0.0)) + 4.0
            ang = math.radians(st.session_state["cfd_angulo"])
            st.session_state["cfd_eye_x"] = 1.5 + 0.3 * math.cos(ang)
            st.session_state["cfd_eye_y"] = -1.8 + 0.3 * math.sin(ang)
            st.rerun()

    db_ctx = load_db_context()
    live_ctx = load_live_context()
    fluid = db_ctx["fluid"]
    signals = db_ctx["signals"]
    session = db_ctx["session"]
    config_df = db_ctx["config_df"]
    live_equity = _safe_float(live_ctx["live_equity"])
    live_unrealized = _safe_float(live_ctx["live_unrealized"])
    portfolio_text = str(live_ctx["portfolio_text"] or "")

    if session.empty:
        st.warning("No hay sesion activa.")
        return

    anchor_equity = _safe_float(session["anchor_equity"].values[0]) or 0.0
    active_uid = str(session["session_uid"].values[0] or "")

    pnl_history, meta = build_reconciled_pnl_series(
        config_df=config_df,
        session_uid=active_uid,
        anchor_equity=anchor_equity,
        live_equity=live_equity,
        live_unrealized=live_unrealized,
    )
    pnl_current = float(pnl_history[-1]) if pnl_history else 0.0
    pnl_prev = float(pnl_history[-2]) if len(pnl_history) > 1 else None
    pnl_delta_pct = ((pnl_current - pnl_prev) / abs(pnl_prev) * 100.0) if (pnl_prev is not None and abs(pnl_prev) > 1e-12) else None
    metrics = _compute_tick_tearsheet_metrics_from_pnl(snapshots=pnl_history, anchor_equity=anchor_equity)
    displayed_equity = live_equity if live_equity is not None else (anchor_equity + pnl_current)

    _debug_log_dashboard(
        hypothesis_id="H_status_mirror_alignment",
        message="dashboard_series_aligned",
        data={
            "session_uid": active_uid[:12],
            "series_source": str(meta.get("series_source")),
            "pnl_current": round(float(pnl_current), 4),
            "pnl_live_now": None if meta.get("pnl_live_now") is None else round(float(meta["pnl_live_now"]), 4),
            "pnl_equity_delta": None if meta.get("pnl_equity_delta") is None else round(float(meta["pnl_equity_delta"]), 4),
            "anchor_equity": round(float(anchor_equity), 4),
            "len": len(pnl_history),
        },
    )

    st.markdown("## DuckClaw CFD Command Center")
    source_chip = str(meta.get("series_source", "fallback")).upper()
    left, right = st.columns([3, 2])
    with left:
        st.caption(f"Sesion activa: `{active_uid}`")
        st.caption(f"Fuente de PnL/tearsheet: `{source_chip}` | Actualizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    with right:
        st.caption(f"Feed IBKR equity: {'LIVE' if live_equity is not None else 'FALLBACK'} | Unrealized: {'LIVE' if live_unrealized is not None else 'N/D'}")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Equity (status espejo)", _fmt_money(displayed_equity))
    with col2:
        st.metric("PnL Sesion (status espejo)", _fmt_money(pnl_current), delta=None if pnl_delta_pct is None else f"{pnl_delta_pct:+.2f}%")
    with col3:
        st.metric("PnL Abierto (IBKR)", _fmt_money(live_unrealized))
    with col4:
        st.metric("Max Drawdown (tick)", _fmt_pct(metrics["max_drawdown_pct"]))

    st.divider()
    c_radar, c_curve = st.columns([2.2, 1.2])

    with c_radar:
        st.subheader("Estado del Fluido: Pseudo-3D (Masa vs Temperatura)")
        default_tickers = [x for x in ["META", "SPY"] if x in list(fluid["ticker"].unique())] if not fluid.empty else []
        selected_tickers = st.multiselect("Activos", fluid["ticker"].unique() if not fluid.empty else [], default=default_tickers)
        show_thresholds = st.checkbox("Mostrar umbrales CFD", value=True)
        df_radar, all_ts, x_mid, x_range = _prepare_radar_dataset(fluid, selected_tickers)
        frame_idx = 0
        if len(all_ts) > 1:
            frame_idx = st.slider("Frame", min_value=0, max_value=len(all_ts) - 1, value=len(all_ts) - 1, step=1)
        camera = dict(
            eye=dict(
                x=float(st.session_state.get("cfd_eye_x", 1.5)),
                y=float(st.session_state.get("cfd_eye_y", -1.8)),
                z=float(st.session_state.get("cfd_eye_z", 0.8)),
            ),
            center=dict(x=0, y=0, z=-0.2),
            up=dict(x=0, y=0, z=1),
        )
        radar_fig = build_animated_radar_3d(
            df_radar,
            frame_idx=frame_idx,
            show_thresholds=show_thresholds,
            camera=camera,
            x_mid=x_mid,
            x_range=x_range,
        )
        df_frame = _frame_state_for_idx(df_radar, all_ts, frame_idx)
        st.plotly_chart(radar_fig, use_container_width=True)
        if len(all_ts) > 0:
            st.caption(f"Timestamp activo: `{all_ts[frame_idx]}`")
        st.markdown("**Leyenda por activo (sincronizada)**")
        if not df_frame.empty:
            for _, row in df_frame.sort_values("ticker").iterrows():
                phase = str(row["phase"]).upper()
                color = _asset_color(str(row["ticker"]))
                st.markdown(
                    f"<span style='color:{color};font-weight:700'>{row['ticker']}</span> - {phase}",
                    unsafe_allow_html=True,
                )
            temp_opt = 0.015
            log_mass_opt = float(x_mid)
            points = [(float(r["y"]), float(r["x"])) for _, r in df_frame.iterrows()]
            energy = 0.0
            if points:
                dists = [
                    math.sqrt(
                        ((temp_now - temp_opt) / 0.035) ** 2 +
                        ((log_mass_now - log_mass_opt) / max(x_range, 1e-6)) ** 2
                    )
                    for temp_now, log_mass_now in points
                ]
                energy = min(100.0, float(np.mean(dists)) * 100.0)
            st.markdown(f"**Energía del sistema:** {energy:.0f}%")
            st.progress(min(max(energy / 100.0, 0.0), 1.0))

    with c_curve:
        st.subheader("Curva de PnL (Tearsheet espejo)")
        pnl_fig = build_pnl_curve(pnl_history)
        st.plotly_chart(pnl_fig, use_container_width=True)

        st.subheader("Riesgo (tick-based)")
        c_r1, c_r2 = st.columns(2)
        c_r1.metric("Sharpe", "N/D" if metrics["sharpe"] is None else f"{metrics['sharpe']:+.2f}")
        c_r2.metric("Volatilidad", _fmt_pct(metrics["volatility_pct"]))
        c_r3, c_r4 = st.columns(2)
        c_r3.metric("Sortino", "N/D" if metrics["sortino"] is None else f"{metrics['sortino']:+.2f}")
        c_r4.metric("PnL previo", _fmt_money(pnl_prev))

    st.divider()
    c_ledger, c_port = st.columns([2, 1])
    with c_ledger:
        st.subheader("Ledger de Senales")
        wanted_cols = [c for c in ["updated_at", "ticker", "action", "status", "rationale"] if c in signals.columns]
        st.dataframe(signals[wanted_cols], height=300, width="stretch")
    with c_port:
        st.subheader("Inventario IBKR")
        st.code(portfolio_text, language="text")

if __name__ == "__main__":
    _debug_log_dashboard(
        hypothesis_id="H_entrypoint_invocation",
        message="python_entrypoint_called",
        data={"argv": [str(x) for x in sys.argv[:6]], "cwd": os.getcwd()},
    )
    main()