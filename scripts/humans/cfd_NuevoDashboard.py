import streamlit as st
import plotly.graph_objects as go
import duckdb
import pandas as pd
import os
import sys
import json
import math
import statistics
from pathlib import Path
from dotenv import load_dotenv
import time
from datetime import datetime

# 1. Configuración de Entorno y Rutas
import sys
from pathlib import Path

# Localizar la raíz del repositorio (3 niveles arriba de este script)
repo_root = Path(__file__).resolve().parent.parent.parent
env_path = repo_root / '.env'
load_dotenv(dotenv_path=env_path)

# 1. Agregar la raíz al path para imports tipo 'packages.agents...'
if str(repo_root) not in sys.path:
    sys.path.append(str(repo_root))

# 2. Agregar todas las carpetas 'src' de los paquetes al path 
# Esto permite que 'import duckclaw' funcione correctamente
packages_dir = repo_root / "packages"
if packages_dir.exists():
    for pkg in packages_dir.iterdir():
        src_path = pkg / "src"
        if src_path.exists():
            # Insertamos al inicio para que tenga prioridad
            sys.path.insert(0, str(src_path))

print(f"--- Sistema de rutas inicializado ---")
print(f"Buscando DB en: {os.getenv('DUCKCLAW_QUANT_SCRIPT_DB')}")


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


st.set_page_config(page_title="DuckClaw Quant Observability", layout="wide", page_icon="🦆")

# Estilo Dark Aeroespacial
st.markdown("""
    <style>
    .main { background-color: #0f172a; color: #f8f9fa; }
    .stMetric { background-color: #1e293b; padding: 15px; border-radius: 10px; border: 1px solid #334155; }
    [data-testid="stMetricValue"] { font-size: 26px; color: #e2e8f0; }
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
    signals = con.execute("SELECT * FROM quant_core.trade_signals ORDER BY updated_at DESC LIMIT 20").df()
    config_all = con.execute("SELECT key, value FROM agent_config").df()
    
    con.close()
    return signals, session, config_all

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
    signals, session, config_df = get_db_data()
    return {"signals": signals, "session": session, "config_df": config_df}


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
    last_x, last_y = steps[-1], float(pnl_history[-1])
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=steps, y=pnl_history, mode="lines", name="PnL ($)",
        line=dict(color="#60a5fa", width=2.5),
        fill="tozeroy",
        fillcolor="rgba(96, 165, 250, 0.18)",
        hovertemplate="<b>Paso %{x}</b><br>PnL: $%{y:,.2f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[last_x],
        y=[last_y],
        mode="markers",
        name="Último",
        marker=dict(size=11, color="#38bdf8", line=dict(color="#f8fafc", width=1)),
        hovertemplate="<b>Último tick</b><br>Paso %{x}<br>PnL: $%{y:,.2f}<extra></extra>",
    ))
    
    fig.add_hline(y=0, line_dash="dash", line_color="rgba(248, 250, 252, 0.35)", line_width=1)
    
    fig.update_layout(
        title=dict(text="PnL sesión (ticks)", font=dict(size=15, color="#e2e8f0")),
        height=420,
        margin=dict(l=0, r=8, t=44, b=12),
        xaxis=dict(title="Paso (Tick)", showgrid=True, gridcolor="rgba(148, 163, 184, 0.12)"),
        yaxis=dict(title="PnL ($)", showgrid=True, gridcolor="rgba(148, 163, 184, 0.12)"),
        paper_bgcolor="rgba(15, 23, 42, 0.5)",
        plot_bgcolor="rgba(30, 41, 59, 0.35)",
        template="plotly_dark",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="right", x=1),
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
    db_ctx = load_db_context()
    live_ctx = load_live_context()
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

    st.markdown("## DuckClaw Quant Observability")
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
    st.subheader("Tearsheet espejo")
    c_pnl, c_risk = st.columns([2, 1])

    with c_pnl:
        st.caption("Serie alineada con `/trading_session --status` (PnL por ticks guardados en agent_config).")
        pnl_fig = build_pnl_curve(pnl_history)
        st.plotly_chart(pnl_fig, use_container_width=True)

    with c_risk:
        st.markdown("**Riesgo (tick-based)**")
        st.caption("Ratios anualizados desde retornos entre puntos de la serie de equity simulada (anchor + PnL).")
        r1, r2 = st.columns(2)
        r1.metric(
            "Sharpe",
            "N/D" if metrics["sharpe"] is None else f"{metrics['sharpe']:+.2f}",
            help="Media/σ de retornos tick anualizada (√252). Requiere ≥3 puntos en la serie.",
        )
        r2.metric(
            "Volatilidad (ann.)",
            _fmt_pct(metrics["volatility_pct"]),
            help="Desviación σ de retornos tick, escalada a anual.",
        )
        r3, r4 = st.columns(2)
        r3.metric(
            "Sortino",
            "N/D" if metrics["sortino"] is None else f"{metrics['sortino']:+.2f}",
            help="Igual que Sharpe pero σ solo en retornos negativos.",
        )
        r4.metric(
            "PnL previo",
            _fmt_money(pnl_prev),
            help="Penúltimo punto de la serie de PnL reconciliada.",
        )
        st.metric(
            "Max drawdown (ticks)",
            _fmt_pct(metrics["max_drawdown_pct"]),
            help="Peor caída desde máximo histórico en la equity reconstruida (anchor + PnL). También en la fila superior.",
        )

    st.divider()
    c_ledger, c_port = st.columns([2, 1])
    with c_ledger:
        st.subheader("Ledger de Senales")
        wanted_cols = [c for c in ["updated_at", "ticker", "action", "status", "rationale"] if c in signals.columns]
        sig_view = signals[wanted_cols] if wanted_cols else signals
        col_cfg: dict = {}
        if "updated_at" in sig_view.columns:
            if pd.api.types.is_datetime64_any_dtype(sig_view["updated_at"]):
                col_cfg["updated_at"] = st.column_config.DatetimeColumn(
                    "Actualizado",
                    format="YYYY-MM-DD HH:mm:ss",
                    width="small",
                )
            else:
                col_cfg["updated_at"] = st.column_config.TextColumn("Actualizado", width="medium")
        if "ticker" in sig_view.columns:
            col_cfg["ticker"] = st.column_config.TextColumn("Ticker", width="small")
        if "action" in sig_view.columns:
            col_cfg["action"] = st.column_config.TextColumn("Acción", width="small")
        if "status" in sig_view.columns:
            col_cfg["status"] = st.column_config.TextColumn("Estado", width="small")
        if "rationale" in sig_view.columns:
            col_cfg["rationale"] = st.column_config.TextColumn(
                "Rationale",
                width="large",
                max_chars=200,
                help="Texto truncado para vista tabular; ver DB para texto completo.",
            )
        st.dataframe(
            sig_view,
            height=300,
            width="stretch",
            hide_index=True,
            column_config=col_cfg if col_cfg else {},
        )
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