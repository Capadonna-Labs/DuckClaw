"""
Overnight Gap Squeeze scanner (live helper).

Script standalone para:
1) leer tickers del portfolio IBKR,
2) estimar fase CFD por ticker con velas 5m (yfinance),
3) persistir estado en `quant_core.fluid_state`,
4) registrar señales BUY/SELL en `quant_core.trade_signals` como `PENDING_HITL`.
"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import pytz
import duckdb
import uuid

# 1. Cargar variables de entorno
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# 2. Añadir la raíz del proyecto al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from packages.agents.src.duckclaw.forge.skills.ibkr_bridge import fetch_ibkr_total_equity_numeric, _get_ibkr_portfolio_impl

# --- CONFIGURACIÓN DEL ALQUIMISTA ---
DIAS_HISTORIA = "5d" 
RIESGO_CAPITAL_PCT = 0.05  # 5% del Equity total por trade propuesto

def apply_kalman_filter(series):
    z = series.values
    n_iter = len(z)
    sz = (n_iter,)
    Q, R = 1e-5, 0.01
    xhat, P, xhatminus, Pminus, K = np.zeros(sz), np.zeros(sz), np.zeros(sz), np.zeros(sz), np.zeros(sz)
    xhat[0], P[0] = z[0], 1.0
    for k in range(1, n_iter):
        xhatminus[k] = xhat[k-1]
        Pminus[k] = P[k-1] + Q
        K[k] = Pminus[k] / (Pminus[k] + R)
        xhat[k] = xhatminus[k] + K[k] * (z[k] - xhatminus[k])
        P[k] = (1 - K[k]) * Pminus[k]
    return pd.Series(xhat, index=series.index)

def get_portfolio_tickers():
    """Extrae los tickers actuales del portafolio de IBKR"""
    print("📡 Escaneando posiciones en IBKR...")
    raw_data = _get_ibkr_portfolio_impl()
    
    # Fallback temporal si el parseo falla
    default_tickers = ["META", "SPY", "TLT", "GLD", "SHY", "IEF", "XLU"]
    
    tickers = []
    for line in raw_data.split('\n'):
        if line.strip().startswith(tuple(str(i)+'.' for i in range(1, 50))):
            try:
                ticker = line.split('.')[1].split(':')[0].strip()
                if ticker != "CASH":
                    tickers.append(ticker)
            except:
                pass
                
    if not tickers:
        print("⚠️ No se pudieron extraer posiciones activas. Usando lista por defecto.")
        return default_tickers
        
    print(f"✅ Tickers detectados: {tickers}")
    return tickers

def analyze_ticker_evolution(ticker, df_today, equity, steps=6):
    """Calcula la evolución del estado en N pasos de tiempo"""
    evolution_data = []
    for i in range(steps, -1, -1):
        end_idx = len(df_today) - i
        if end_idx < 6: continue
        
        df_step = df_today.iloc[end_idx-6 : end_idx].copy()
        df_step['Net_Volume'] = np.where(df_step['Close'] > df_step['Open'], df_step['Volume'], -df_step['Volume'])
        masa = df_step['Net_Volume'].sum()
        tendencia = df_step['Kalman'].iloc[-1] - df_step['Kalman'].iloc[0]
        
        evolution_data.append({
            "Ticker": ticker,
            "Vol_Neto": masa,
            "Tendencia": tendencia,
            "Precio": df_step['Close'].iloc[-1],
            "Step": i 
        })
    return evolution_data

def project_future_taylor(evolution_data):
    if len(evolution_data) < 3: return None
    df_ev = pd.DataFrame(evolution_data)
    x_steps = np.arange(len(df_ev))
    poly_masa = np.polyfit(x_steps, df_ev['Vol_Neto'], 2)
    next_masa = np.polyval(poly_masa, len(x_steps))
    poly_trend = np.polyfit(x_steps, df_ev['Tendencia'], 2)
    next_trend = np.polyval(poly_trend, len(x_steps))
    return next_masa, next_trend

def plot_thermodynamic_polar(all_evolutions):
    """Dibuja el Radar de Fase con estelas de trayectoria."""
    fig = plt.figure(figsize=(12, 10), facecolor='#f8f9fa')
    ax = fig.add_subplot(111, projection='polar')
    
    max_masa = 0
    for steps in all_evolutions.values():
        max_masa = max(max_masa, max(abs(s['Vol_Neto']) for s in steps))
    
    for ticker, steps in all_evolutions.items():
        df_ev = pd.DataFrame(steps)
        rs = abs(df_ev['Vol_Neto']) / max_masa
        thetas = np.arctan2(df_ev['Tendencia'], df_ev['Vol_Neto'])
        
        ax.plot(thetas, rs, color='black', alpha=0.2, linestyle='-', linewidth=1.5, zorder=1)
        
        current_r = rs.iloc[-1]
        current_theta = thetas.iloc[-1]
        color = '#22c55e' if 0 <= current_theta <= np.pi/2 else '#ef4444' if -np.pi <= current_theta <= -np.pi/2 else '#64748b'
        
        ax.scatter(current_theta, current_r, s=current_r * 600 + 200, c=color, alpha=0.9, edgecolors='white', linewidth=1.5, zorder=5)

        projection = project_future_taylor(steps)
        if projection:
            p_masa, p_trend = projection
            p_r = abs(p_masa) / max_masa
            p_theta = np.arctan2(p_trend, p_masa)
            ax.annotate("", xy=(p_theta, p_r), xytext=(current_theta, current_r),
                        arrowprops=dict(arrowstyle="->,head_width=0.5,head_length=0.7", color='orange', lw=3, alpha=0.8, linestyle='--'))

        ax.annotate(ticker, (current_theta, current_r), xytext=(10, 10), textcoords='offset points', fontsize=11, fontweight='bold')

    ax.set_theta_zero_location("E") 
    ax.set_thetagrids([0, 90, 180, 270], ["Masa + (Vol)", "Inercia + (Trend)", "Masa -", "Inercia -"])
    ax.set_yticklabels([]) 
    ax.set_title("Reactor CFD: Trayectoria y Proyección de Taylor", va='bottom', fontsize=16, fontweight='bold', pad=40)
    plt.tight_layout()
    plt.show()

def main():
    print("🌊 Iniciando Escáner de Dinámica de Fluidos Multi-Activo...")
    
    equity, err = fetch_ibkr_total_equity_numeric()
    if equity is None:
        print(f"⚠️ Advertencia: No se pudo conectar a IBKR. Usando capital simulado.")
        equity = 10000.0
    else:
        print(f"✅ Equity detectado: ${equity:,.2f} USD")

    tickers = get_portfolio_tickers()
    bogota_tz = pytz.timezone('America/Bogota')
    
    all_evolutions = {} 
    latest_signals = [] 
    
    print("\n🔍 Analizando termodinámica y trayectoria de activos...")
    for ticker in tickers:
        try:
            df = yf.download(ticker, period=DIAS_HISTORIA, interval="5m", progress=False)
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            
            if df.index.tz is None: df.index = df.index.tz_localize('UTC')
            df.index = df.index.tz_convert(bogota_tz)
            
            df['Kalman'] = apply_kalman_filter(df['Close'])
            last_day = df.index[-1].date()
            df_today = df[df.index.date == last_day].copy()
            
            evolution = analyze_ticker_evolution(ticker, df_today, equity, steps=6)
            if evolution:
                all_evolutions[ticker] = evolution
                current_state = evolution[-1]
                
                fase = "GAS" if current_state['Vol_Neto'] > 0 and current_state['Tendencia'] > 0 else \
                       "PLASMA" if current_state['Vol_Neto'] < 0 and current_state['Tendencia'] < 0 else "SÓLIDA"
                
                signal = "BUY" if fase == "GAS" else "SELL" if fase == "PLASMA" else "HOLD"
                
                latest_signals.append({
                    "Ticker": ticker, "Señal": signal, "Fase": fase,
                    "Qty": int((equity * RIESGO_CAPITAL_PCT) // current_state['Precio']) if signal != "HOLD" else 0,
                    "Precio": current_state['Precio'], "Tendencia": current_state['Tendencia'], "Vol_Neto": current_state['Vol_Neto']
                })
                icon = "🔥" if signal == "BUY" else "🧊" if signal == "SELL" else "⚖️ "
                print(f"  {icon} {ticker:<5} | Fase: {fase:<6} | Trayectoria OK")
        except Exception as e:
            print(f"  ❌ {ticker:<5} | Error: {str(e)}")

    df_signals = pd.DataFrame(latest_signals)
    if not df_signals.empty:
        df_signals.set_index('Ticker', inplace=True)
        
        # --- BLOQUE DE PERSISTENCIA (DUAL: FLUID_STATE + TRADE_SIGNALS) ---
        db_path = os.environ.get("DUCKCLAW_QUANT_SCRIPT_DB")
        if db_path and os.path.exists(db_path):
            try:
                con = duckdb.connect(db_path, read_only=False)
                
                # 1. Obtener session_uid activo
                res = con.execute("SELECT session_uid FROM quant_core.trading_sessions WHERE id = 'active' AND status = 'ACTIVE'").fetchone()
                active_session_uid = res[0] if res else "manual_script"

                for ticker, row in df_signals.iterrows():
                    # A. Persistir en fluid_state (Para la película del Dashboard)
                    ts_now = datetime.now(bogota_tz).strftime('%Y-%m-%d %H:%M:%S')
                    con.execute("""
                        INSERT INTO quant_core.fluid_state (ticker, timestamp, hex_signature, mass, temperature, phase)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (ticker, ts_now, str(uuid.uuid4())[:8], float(row['Vol_Neto']), float(row['Tendencia']), row['Fase']))

                    # B. Persistir en trade_signals (Para el ejecutor manual)
                    if "BUY" in row['Señal'] or "SELL" in row['Señal']:
                        con.execute("""
                            INSERT INTO quant_core.trade_signals (signal_id, ticker, action, order_qty, status, rationale, session_uid, strategy_name) 
                            VALUES (?, ?, ?, ?, 'PENDING_HITL', ?, ?, 'overnight_squeeze')
                        """, (str(uuid.uuid4()), ticker, row['Señal'], float(row['Qty']), f"Fase: {row['Fase']} | Trend: {row['Tendencia']:.3f}", active_session_uid))
                
                con.close()
                print("💾 Ledger y Fluid State actualizados.")
            except Exception as e: print(f"❌ Error DB: {e}")

        plot_thermodynamic_polar(all_evolutions)
    else:
        print("❌ No se generaron datos suficientes.")

if __name__ == "__main__":
    main()