import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
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

# 1. Configuración de Entorno
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from packages.agents.src.duckclaw.forge.skills.ibkr_bridge import (
    fetch_ibkr_total_equity_numeric, 
    _get_ibkr_portfolio_impl
)

st.set_page_config(page_title="DuckClaw CFD Command Center", layout="wide", page_icon="🦆")

# Estilo Dark Aeroespacial con Alerta de Drawdown
st.markdown("""
    <style>
    .main { background-color: #0f172a; color: #f8f9fa; }
    .stMetric { background-color: #1e293b; padding: 15px; border-radius: 10px; border: 1px solid #334155; }
    [data-testid="stMetricValue"] { font-size: 24px; }
    </style>
    """, unsafe_allow_html=True)

def get_db_data():
    db_path = os.environ.get("DUCKCLAW_QUANT_SCRIPT_DB")
    con = duckdb.connect(db_path, read_only=True)
    
    # 1. Obtener la sesión activa y su UID
    session = con.execute("SELECT anchor_equity, session_uid FROM quant_core.trading_sessions WHERE id = 'active' AND status = 'ACTIVE'").df()
    
    if session.empty:
        con.close()
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), ""

    active_uid = session['session_uid'].values[0]
    anchor_equity = session['anchor_equity'].values[0]

    # 2. Buscar en agent_config los datos vinculados a este session_uid
    # Buscamos la clave que termina en 'trading_session_pnl_hist_uid' y tiene el valor active_uid
    config_all = con.execute("SELECT key, value FROM agent_config").df()
    
    try:
        # Identificar el prefijo del chat (chat_ID_)
        uid_row = config_all[config_all['value'] == active_uid]
        chat_prefix = uid_row['key'].values[0].replace('trading_session_pnl_hist_uid', '')
        
        # Extraer PnL y Snapshots usando ese prefijo
        last_pnl = float(config_all[config_all['key'] == f"{chat_prefix}trading_session_last_pnl"]['value'].values[0])
        snapshots_json = config_all[config_all['key'] == f"{chat_prefix}trading_session_pnl_snapshots_json"]['value'].values[0]
        pnl_history = json.loads(snapshots_json)
    except:
        last_pnl, pnl_history = 0.0, []

    fluid_state = con.execute("SELECT * FROM quant_core.fluid_state ORDER BY timestamp ASC").df()
    signals = con.execute("SELECT * FROM quant_core.trade_signals ORDER BY updated_at DESC LIMIT 20").df()
    
    con.close()
    return fluid_state, signals, session, pnl_history, last_pnl

def calculate_tearsheet_sync(snapshots, anchor_equity):
    """Replica exacta de la lógica de on_the_fly_commands.py"""
    out = {"sharpe": 0.0, "sortino": 0.0, "volatility_pct": 0.0, "max_drawdown_pct": 0.0}
    if anchor_equity <= 0 or len(snapshots) < 3: return out
    
    equity_curve = [anchor_equity + float(p) for p in snapshots]
    returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i-1]
        if prev > 0: returns.append((equity_curve[i] / prev) - 1.0)
    
    if len(returns) < 2: return out
    mean_r, std_r = statistics.fmean(returns), statistics.pstdev(returns)
    
    if std_r > 1e-12:
        out["sharpe"] = (mean_r / std_r) * math.sqrt(252.0)
        out["volatility_pct"] = std_r * math.sqrt(252.0) * 100.0
    
    downside = [r for r in returns if r < 0]
    if downside:
        std_down = statistics.pstdev(downside)
        if std_down > 1e-12: out["sortino"] = (mean_r / std_down) * math.sqrt(252.0)
            
    peak, mdd = equity_curve[0], 0.0
    for v in equity_curve:
        if v > peak: peak = v
        if peak > 0:
            dd = (v / peak) - 1.0
            if dd < mdd: mdd = dd
    out["max_drawdown_pct"] = mdd * 100.0
    return out

def main():
    st.sidebar.title("🎮 Operación Manual")
    if st.sidebar.button("🔄 Refrescar Telemetría", use_container_width=True): st.rerun()

    fluid, signals, session, pnl_history, bot_pnl = get_db_data()
    live_equity, _ = fetch_ibkr_total_equity_numeric()
    portfolio_text = _get_ibkr_portfolio_impl()

    if session.empty:
        st.warning("⚠️ No hay sesión activa.")
        return

    anchor_equity = session['anchor_equity'].values[0]
    metrics = calculate_tearsheet_sync(pnl_history, anchor_equity)

    # --- FILA 1: KPI REALES (Sincronizados con Telegram) ---
    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Equity Real (IBKR)", f"${live_equity:,.2f}" if live_equity else "N/A")
    with col2: st.metric("PnL Sesión (Bot Sync)", f"${bot_pnl:,.2f}", delta_color="inverse")
    with col3: st.metric("Sharpe (Tick-based)", f"{metrics['sharpe']:+.2f}")
    with col4: st.metric("Max Drawdown", f"{metrics['max_drawdown_pct']:.2f}%")

    # --- FILA 2: MÉTRICAS DE RIESGO ---
    col5, col6, col7, col8 = st.columns(4)
    with col5: st.metric("Sortino", f"{metrics['sortino']:+.2f}")
    with col6: st.metric("Volatilidad", f"{metrics['volatility_pct']:.2f}%")
    with col7: st.metric("Ticks de Sesión", len(pnl_history))
    with col8: st.metric("Estado", "CRÍTICO" if metrics['max_drawdown_pct'] < -1.0 else "NOMINAL")

    # --- FILA 3: RADAR Y LEDGER ---
    st.divider()
    c_radar, c_ledger = st.columns([2, 1])
    
    with c_radar:
        st.subheader("🛰️ Radar CFD: Evolución de Fase")
        selected_tickers = st.multiselect("Activos", fluid['ticker'].unique(), default=["META"])
        if not fluid.empty and selected_tickers:
            df_plot = fluid[fluid['ticker'].isin(selected_tickers)].copy()
            df_plot['display_size'] = df_plot['mass'].abs() + 1
            df_plot['ts_str'] = df_plot['timestamp'].astype(str)
            fig = px.scatter(df_plot, x="mass", y="temperature", animation_frame="ts_str", animation_group="ticker",
                             color="phase", text="ticker", size="display_size",
                             color_discrete_map={"GAS": "#22c55e", "PLASMA": "#ef4444", "SOLID": "#3b82f6", "LIQUID": "#f59e0b"},
                             template="plotly_dark", range_x=[fluid['mass'].min()*1.2, fluid['mass'].max()*1.2], range_y=[fluid['temperature'].min()*1.2, fluid['temperature'].max()*1.2])
            fig.update_layout(height=500, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

    with c_ledger:
        st.subheader("📜 Ledger de Señales")
        st.dataframe(signals[['updated_at', 'ticker', 'action', 'status', 'rationale']], height=500)

    st.subheader("🏦 Inventario IBKR")
    st.code(portfolio_text, language="text")

if __name__ == "__main__":
    main()