import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import duckdb
import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

# 1. Configuración de Entorno
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from packages.agents.src.duckclaw.forge.skills.ibkr_bridge import (
    fetch_ibkr_total_equity_numeric, 
    _get_ibkr_portfolio_impl
)

st.set_page_config(page_title="DuckClaw CFD Radar", layout="wide", page_icon="🦆")

# Estilo Dark Aeroespacial
st.markdown("""
    <style>
    .main { background-color: #0f172a; color: #f8f9fa; }
    .stMetric { background-color: #1e293b; padding: 15px; border-radius: 10px; border: 1px solid #334155; }
    [data-testid="stMetricValue"] { font-size: 28px; color: #60a5fa; }
    </style>
    """, unsafe_allow_html=True)

def get_db_data():
    db_path = os.environ.get("DUCKCLAW_QUANT_SCRIPT_DB")
    con = duckdb.connect(db_path, read_only=True)
    fluid_state = con.execute("SELECT * FROM quant_core.fluid_state ORDER BY timestamp ASC").df()
    signals = con.execute("SELECT * FROM quant_core.trade_signals ORDER BY updated_at DESC LIMIT 20").df()
    session = con.execute("SELECT mode, anchor_equity, session_uid FROM quant_core.trading_sessions WHERE id = 'active'").df()
    con.close()
    return fluid_state, signals, session

def build_animated_radar(df, selected_tickers):
    if df.empty or not selected_tickers: return go.Figure()
    
    df_plot = df[df['ticker'].isin(selected_tickers)].copy()
    df_plot['timestamp_str'] = df_plot['timestamp'].astype(str)
    
    max_mass = df_plot['mass'].abs().max() if not df_plot['mass'].empty else 1
    max_temp = df_plot['temperature'].abs().max() if not df_plot['temperature'].empty else 1
    df_plot['x'] = df_plot['mass'] / max_mass
    df_plot['y'] = df_plot['temperature'] / max_temp
    
    fig = px.scatter(df_plot, x="x", y="y", 
                     animation_frame="timestamp_str", 
                     animation_group="ticker",
                     color="phase", hover_name="ticker", text="ticker",
                     size_max=40, range_x=[-1.2, 1.2], range_y=[-1.2, 1.2],
                     color_discrete_map={"GAS": "#22c55e", "PLASMA": "#ef4444", "SOLID": "#3b82f6", "LIQUID": "#f59e0b"},
                     template="plotly_dark")

    for r in [0.25, 0.5, 0.75, 1.0]:
        theta = np.linspace(0, 2*np.pi, 100)
        fig.add_trace(go.Scatter(x=r*np.cos(theta), y=r*np.sin(theta), 
                                 mode='lines', line=dict(color='rgba(255,255,255,0.05)', width=1),
                                 showlegend=False, hoverinfo='skip'))

    fig.update_layout(height=600, margin=dict(l=0, r=0, t=30, b=0),
                      xaxis=dict(visible=False), yaxis=dict(visible=False),
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return fig

def main():
    st.sidebar.title("🎮 Control de Misión")
    if st.sidebar.button("🔄 Refrescar Datos", use_container_width=True): st.rerun()

    fluid, signals, session = get_db_data()
    live_equity_val, _ = fetch_ibkr_total_equity_numeric()
    portfolio_text = _get_ibkr_portfolio_impl()

    # --- CÁLCULO DE PNL REAL (Math Sync) ---
    anchor_equity = session['anchor_equity'].values[0] if not session.empty else 0.0
    if live_equity_val and anchor_equity > 0:
        real_pnl = live_equity_val - anchor_equity
    else:
        real_pnl = 0.0

    # --- FILTROS ---
    posiciones_reales = [t for t in fluid['ticker'].unique() if t in portfolio_text]
    ver_solo_posiciones = st.sidebar.toggle("Ver solo activos en Portfolio", value=True)
    selected_tickers = st.sidebar.multiselect("Tickers en Radar", 
                                              fluid['ticker'].unique().tolist(), 
                                              default=posiciones_reales if ver_solo_posiciones else fluid['ticker'].unique().tolist())

    # --- MÉTRICAS ---
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Equity Real (IBKR)", f"${live_equity_val:,.2f}" if live_equity_val else "N/A")
    with col2: st.metric("PnL de Sesión (Sincronizado)", f"${real_pnl:,.2f}", delta_color="normal" if real_pnl >= 0 else "inverse")
    with col3: st.metric("Estado", "NOMINAL", delta="Tailscale Mesh OK")

    # --- RADAR ---
    st.subheader("🛰️ Radar CFD: Evolución Temporal")
    ticks_count = len(fluid[fluid['ticker'].isin(selected_tickers)]['timestamp'].unique())
    if ticks_count < 2:
        st.info(f"ℹ️ Ticks: {ticks_count}. Corre 'overnight_squeeze_live.py' para activar el botón Play.")
    
    radar_fig = build_animated_radar(fluid, selected_tickers)
    st.plotly_chart(radar_fig, use_container_width=True)

    # --- LEDGER Y PORTFOLIO ---
    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("📜 Ledger de Señales")
        st.dataframe(signals[['updated_at', 'ticker', 'action', 'status', 'rationale']], use_container_width=True)
    with c2:
        st.subheader("🏦 Inventario IBKR")
        st.code(portfolio_text, language="text")

if __name__ == "__main__":
    main()