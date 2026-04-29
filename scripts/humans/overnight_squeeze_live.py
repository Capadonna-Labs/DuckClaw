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
import matplotlib.dates as mdates
import pytz
import duckdb
import uuid

# 1. Cargar variables de entorno
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# 2. Añadir la raíz del proyecto al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from packages.agents.src.duckclaw.forge.skills.ibkr_bridge import fetch_ibkr_total_equity_numeric, _get_ibkr_portfolio_impl
import json

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
    Extrae los tickers actuales del portafolio de IBKR
    print("📡 Escaneando posiciones en IBKR...")
    raw_data = _get_ibkr_portfolio_impl()
    
    # El bridge devuelve un string formateado para Telegram, necesitamos extraer los tickers.
    # Una forma más limpia sería usar la función interna que devuelve el JSON, 
    # pero para este script standalone, parsearemos el texto o usaremos un fallback.
    
    # Fallback temporal si el parseo falla (asegúrate de tener estos en tu cuenta paper)
    default_tickers =["META", "SPY", "TLT", "GLD", "SHY", "IEF", "XLU"]
    
    # Intento de extracción simple del texto formateado
    tickers =[]
    for line in raw_data.split('\n'):
        if line.strip().startswith(tuple(str(i)+'.' for i in range(1, 50))):
            # Ejemplo de línea: "  1. META: 20.0 unidades..."
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

def analyze_ticker(ticker, equity, bogota_tz, ny_tz):
    #Ejecuta el análisis CFD para un solo ticker
    try:
        df = yf.download(ticker, period=DIAS_HISTORIA, interval="5m", progress=False)
        if df.empty:
            return None
    except Exception:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    df.index = df.index.tz_convert(bogota_tz)

    df['Kalman'] = apply_kalman_filter(df['Close'])
    
    last_day = df.index[-1].date()
    df_today = df[df.index.date == last_day].copy()
    
    if df_today.empty or len(df_today) < 2:
        return None

    last_timestamp_ny = df_today.index[-1].astimezone(ny_tz)
    market_close_ny = last_timestamp_ny.replace(hour=16, minute=0, second=0, microsecond=0)
    moc_start_ny = last_timestamp_ny.replace(hour=15, minute=30, second=0, microsecond=0)
    
    market_close = market_close_ny.astimezone(bogota_tz)
    moc_start = moc_start_ny.astimezone(bogota_tz)
    last_timestamp = df_today.index[-1]
    
    if last_timestamp < moc_start:
        fase_sesion = "INTRADÍA"
        df_analysis = df_today.iloc[-6:].copy() 
    elif last_timestamp >= moc_start and last_timestamp <= market_close:
        fase_sesion = "MOC"
        df_analysis = df_today[df_today.index >= moc_start].copy()
    else:
        fase_sesion = "POST-MERCADO"
        df_analysis = df_today[(df_today.index >= moc_start) & (df_today.index <= market_close)].copy()

    if df_analysis.empty:
        df_analysis = df_today.iloc[-6:].copy()

    df_analysis['Net_Volume'] = np.where(df_analysis['Close'] > df_analysis['Open'], 
                                           df_analysis['Volume'], 
                                           -df_analysis['Volume'])
    
    cumulative_net_volume = df_analysis['Net_Volume'].sum()
    price_trend = df_analysis['Kalman'].iloc[-1] - df_analysis['Kalman'].iloc[0]
    current_price = df_today['Close'].iloc[-1]
    
    # --- VÁLVULA TEMPORAL (MOC GATE) ---
    # Solo permitimos BUY/SELL si estamos en la ventana MOC (15:30 - 16:00 NY)
    # En cualquier otra hora, el veredicto es informativo (HOLD)
    is_moc_window = (fase_sesion == "MOC")
    
    if cumulative_net_volume > 0 and price_trend > 0:
        fase_fluido = "GAS"
        # Solo se vuelve señal de acción si es la hora del cierre
        signal = "BUY" if is_moc_window else "HOLD (Esperando MOC)"
    elif cumulative_net_volume < 0 and price_trend < 0:
        fase_fluido = "PLASMA"
        signal = "SELL" if is_moc_window else "HOLD (Esperando MOC)"
    else:
        fase_fluido = "SÓLIDA"
        signal = "HOLD"

    capital_asignado = equity * RIESGO_CAPITAL_PCT
    qty_propuesta = int(capital_asignado // current_price) if current_price > 0 else 0

    return {
        "Ticker": ticker,
        "Fase": fase_fluido,
        "Señal": signal,
        "Tendencia": price_trend,
        "Vol_Neto": cumulative_net_volume,
        "Qty": qty_propuesta if "HOLD" not in signal else 0,
        "Precio": current_price
    }

def plot_thermodynamic_scatter(df_res):
    #Genera un gráfico de dispersión cruzando Tendencia vs Volumen Neto
    if df_res is None or (isinstance(df_res, pd.DataFrame) and df_res.empty):
        return

    fig, ax = plt.subplots(figsize=(12, 8))
    
    # Colores basados en la lógica de fase
    def get_color(row):
        if row['Vol_Neto'] > 0 and row['Tendencia'] > 0: return 'green'
        if row['Vol_Neto'] < 0 and row['Tendencia'] < 0: return 'red'
        return 'gray'
    
    colors = df_res.apply(get_color, axis=1)
    
    # Scatter plot
    ax.scatter(df_res['Vol_Neto'], df_res['Tendencia'], 
               s=abs(df_res['Vol_Neto']) / (df_res['Vol_Neto'].abs().max() + 1) * 1000 + 100, 
               c=colors, alpha=0.6, edgecolors='black')
    
    ax.axhline(0, color='black', linestyle='--', alpha=0.3)
    ax.axvline(0, color='black', linestyle='--', alpha=0.3)
    
    for i, txt in enumerate(df_res['Ticker']):
        ax.annotate(txt, (df_res['Vol_Neto'].iloc[i], df_res['Tendencia'].iloc[i]), 
                    xytext=(5, 5), textcoords='offset points', fontsize=10, fontweight='bold')
    
    # Etiquetas de Cuadrantes
    ax.text(0.95, 0.95, 'Fase GAS (Squeeze)\nVol+ / Trend+', transform=ax.transAxes, color='green', ha='right', va='top', alpha=0.5)
    ax.text(0.05, 0.05, 'Fase PLASMA (Dump)\nVol- / Trend-', transform=ax.transAxes, color='red', ha='left', va='bottom', alpha=0.5)

    ax.set_title("Mapa Termodinámico del Portafolio", fontsize=14)
    ax.set_xlabel("Masa Neta (Volumen Direccional)", fontsize=12)
    ax.set_ylabel("Inercia Térmica (Delta Kalman)", fontsize=12)
    ax.grid(True, alpha=0.2)
    
    plt.tight_layout()
    plt.show()

def analyze_ticker_evolution(ticker, df_today, equity, steps=5):
    Calcula la evolución del estado en N pasos de tiempo (ventanas deslizantes)
    evolution_data = []
    
    # Cada paso retrocede 1 vela (5 min) para ver la micro-evolución
    for i in range(steps, -1, -1):
        # Definir la ventana para este paso
        end_idx = len(df_today) - i
        if end_idx < 6: continue
        
        df_step = df_today.iloc[end_idx-6 : end_idx].copy()
        
        # Cálculos CFD
        df_step['Net_Volume'] = np.where(df_step['Close'] > df_step['Open'], df_step['Volume'], -df_step['Volume'])
        masa = df_step['Net_Volume'].sum()
        tendencia = df_step['Kalman'].iloc[-1] - df_step['Kalman'].iloc[0]
        
        evolution_data.append({
            "Ticker": ticker,
            "Vol_Neto": masa,
            "Tendencia": tendencia,
            "Precio": df_step['Close'].iloc[-1],
            "Step": i # 0 es el actual, mayor es más antiguo
        })
    return evolution_data

def project_future_taylor(evolution_data):
    Usa una aproximación de Taylor (polinomio de grado 2) 
    para proyectar el siguiente estado del fluido.
    if len(evolution_data) < 3: return None
    
    df_ev = pd.DataFrame(evolution_data)
    # Invertimos el orden para que el tiempo sea ascendente (0, 1, 2...)
    x_steps = np.arange(len(df_ev))
    
    # Proyectar Masa (Vol_Neto)
    poly_masa = np.polyfit(x_steps, df_ev['Vol_Neto'], 2)
    next_masa = np.polyval(poly_masa, len(x_steps))
    
    # Proyectar Inercia (Tendencia)
    poly_trend = np.polyfit(x_steps, df_ev['Tendencia'], 2)
    next_trend = np.polyval(poly_trend, len(x_steps))
    
    return next_masa, next_trend
def plot_thermodynamic_polar(all_evolutions):
    Dibuja el mapa termodinámico alineado a ejes cartesianos (Radar de Fase)
    fig = plt.figure(figsize=(12, 10))
    ax = fig.add_subplot(111, projection='polar')
    
    max_masa = 0
    for steps in all_evolutions.values():
        max_masa = max(max_masa, max(abs(s['Vol_Neto']) for s in steps))
    
    for ticker, steps in all_evolutions.items():
        df_ev = pd.DataFrame(steps)
        r = abs(df_ev['Vol_Neto']) / max_masa
        theta = np.arctan2(df_ev['Tendencia'], df_ev['Vol_Neto'])
        
        ax.plot(theta, r, alpha=0.3, linestyle=':', linewidth=1)
        
        current_r = r.iloc[-1]
        current_theta = theta.iloc[-1]
        
        color = 'green' if 0 <= current_theta <= np.pi/2 else \
                'red' if -np.pi <= current_theta <= -np.pi/2 else 'gray'
        
        ax.scatter(current_theta, current_r, s=current_r * 500 + 100, 
                   c=color, alpha=0.8, edgecolors='black', zorder=5)

        projection = project_future_taylor(steps)
        if projection:
            p_masa, p_trend = projection
            p_r = abs(p_masa) / max_masa
            p_theta = np.arctan2(p_trend, p_masa)
            ax.annotate("", xy=(p_theta, p_r), xytext=(current_theta, current_r),
                        arrowprops=dict(arrowstyle="->", color=color, lw=2, linestyle='--'))

        ax.annotate(ticker, (current_theta, current_r), fontsize=10, fontweight='bold')

    # --- ALINEACIÓN CARTESIANA ---
    ax.set_theta_zero_location("E") # 0° a la derecha (Eje X positivo)
    
    # Dibujar la cruz cartesiana (0, 90, 180, 270)
    ax.set_thetagrids([0, 90, 180, 270],["Masa + (Vol)", "Inercia + (Trend)", "Masa -", "Inercia -"])
    
    # Colocar las etiquetas de fase flotando en los cuadrantes
    ax.text(np.pi/4, 1.15, "GAS\n(Squeeze)", ha='center', va='center', color='green', fontweight='bold')
    ax.text(3*np.pi/4, 1.15, "DIV-\n(Fricción)", ha='center', va='center', color='gray', fontweight='bold')
    ax.text(5*np.pi/4, 1.15, "PLASMA\n(Dump)", ha='center', va='center', color='red', fontweight='bold')
    ax.text(7*np.pi/4, 1.15, "DIV+\n(Acumulación)", ha='center', va='center', color='gray', fontweight='bold')
    
    ax.set_yticklabels([]) # Ocultar radios numéricos
    ax.set_title("Radar CFD: Fase y Energía del Portafolio", va='bottom', fontsize=15, pad=30)
    
    plt.show()

def plot_thermodynamic_polar(all_evolutions):
    Dibuja el Radar de Fase con estelas de trayectoria y proyecciones de Taylor mejoradas.
    fig = plt.figure(figsize=(12, 10), facecolor='#f8f9fa')
    ax = fig.add_subplot(111, projection='polar')
    
    # 1. Normalización de Masa
    max_masa = 0
    for steps in all_evolutions.values():
        max_masa = max(max_masa, max(abs(s['Vol_Neto']) for s in steps))
    
    for ticker, steps in all_evolutions.items():
        df_ev = pd.DataFrame(steps)
        
        # Convertir toda la historia a polares para la estela
        rs = abs(df_ev['Vol_Neto']) / max_masa
        thetas = np.arctan2(df_ev['Tendencia'], df_ev['Vol_Neto'])
        
        # --- DIBUJAR ESTELA (TRAYECTORIA HISTÓRICA) ---
        # Usamos un degradado visual: la línea se vuelve más sólida cerca del presente
        ax.plot(thetas, rs, color='black', alpha=0.2, linestyle='-', linewidth=1.5, zorder=1)
        
        # Punto actual
        current_r = rs.iloc[-1]
        current_theta = thetas.iloc[-1]
        
        # Color según fase actual
        color = '#22c55e' if 0 <= current_theta <= np.pi/2 else \
                '#ef4444' if -np.pi <= current_theta <= -np.pi/2 else '#64748b'
        
        # Dibujar el "puntero" actual (más grande para destacar)
        ax.scatter(current_theta, current_r, s=current_r * 600 + 200, 
                   c=color, alpha=0.9, edgecolors='white', linewidth=1.5, zorder=5)

        # --- PROYECCIÓN DE TAYLOR (VECTOR DE INTENTO T+1) ---
        projection = project_future_taylor(steps)
        if projection:
            p_masa, p_trend = projection
            p_r = abs(p_masa) / max_masa
            p_theta = np.arctan2(p_trend, p_masa)
            
            # Flecha de Taylor: Aumentamos grosor y usamos un estilo de flecha más visible
            # Usamos un color que destaque (ej: 'gold' o 'cyan') para que no se pierda
            ax.annotate("", 
                        xy=(p_theta, p_r), 
                        xytext=(current_theta, current_r),
                        arrowprops=dict(
                            arrowstyle="->,head_width=0.5,head_length=0.7",
                            color='orange', # Color de advertencia/proyección
                            lw=3,           # Grosor aumentado
                            alpha=0.8,
                            linestyle='--'
                        ),
                        zorder=6)
            
            # Marcador de destino proyectado
            ax.scatter(p_theta, p_r, s=100, color='orange', marker='x', alpha=0.5, zorder=6)

        # Etiqueta del Ticker
        ax.annotate(ticker, (current_theta, current_r), 
                    xytext=(10, 10), textcoords='offset points',
                    fontsize=11, fontweight='bold', color='#1e293b')

    # --- CONFIGURACIÓN DEL RADAR CARTESIANO ---
    ax.set_theta_zero_location("E") 
    ax.set_thetagrids([0, 90, 180, 270], ["Masa + (Vol)", "Inercia + (Trend)", "Masa -", "Inercia -"])
    
    # Etiquetas de Fase en los cuadrantes
    ax.text(np.pi/4, 1.2, "GAS\n(Squeeze)", ha='center', va='center', color='#16a34a', fontweight='bold', fontsize=12)
    ax.text(3*np.pi/4, 1.2, "DIV-\n(Fricción)", ha='center', va='center', color='#475569', fontweight='bold', fontsize=12)
    ax.text(5*np.pi/4, 1.2, "PLASMA\n(Dump)", ha='center', va='center', color='#dc2626', fontweight='bold', fontsize=12)
    ax.text(7*np.pi/4, 1.2, "DIV+\n(Acumulación)", ha='center', va='center', color='#475569', fontweight='bold', fontsize=12)
    
    ax.set_yticklabels([]) 
    ax.set_title("Reactor CFD: Trayectoria y Proyección de Taylor", va='bottom', fontsize=16, fontweight='bold', pad=40)
    ax.grid(True, alpha=0.3, linestyle='--')
    
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
    ny_tz = pytz.timezone('America/New_York')
    
    resultados = []
    print("\n🔍 Analizando termodinámica de activos...")
    for ticker in tickers:
        try:
            #res = analyze_ticker(ticker, equity, bogota_tz, ny_tz)
            res = analyze_ticker_evolution(ticker, df_today, equity)
            if res:
                resultados.append(res)
                icon = "🔥" if res['Señal'] == "BUY" else "🧊" if res['Señal'] == "SELL" else "⚖️ "
                print(f"  {icon} {ticker:<5} | Fase: {res['Fase']:<6} | Señal: {res['Señal']:<4} | Vol Neto: {res['Vol_Neto']:>10,.0f}")
        except Exception as e:
            print(f"  ❌ {ticker:<5} | Error: {str(e)[:50]}")

    df_signals = pd.DataFrame(resultados)
    if not df_signals.empty:
        df_signals.set_index('Ticker', inplace=True)
        
        print("\n" + "="*70)
        print("   SERIE DE SEÑALES ESTRUCTURADAS (DATAFRAME)")
        print("="*70)
        df_display = df_signals.copy()
        df_display['Vol_Neto'] = df_display['Vol_Neto'].apply(lambda x: f"{x:,.0f}")
        df_display['Tendencia'] = df_display['Tendencia'].apply(lambda x: f"{x:.3f}")
        df_display['Precio'] = df_display['Precio'].apply(lambda x: f"${x:.2f}")
        print(df_display[['Señal', 'Fase', 'Qty', 'Precio', 'Tendencia', 'Vol_Neto']])
        print("="*70)
        
        # --- INYECCIÓN AL LEDGER ---
        db_path = os.environ.get("DUCKCLAW_QUANT_SCRIPT_DB")
        if db_path and os.path.exists(db_path):
            print(f"\n💾 Inyectando señales en el Ledger: {db_path}")
            try:
                con = duckdb.connect(db_path, read_only=False)
                signals_to_inject = df_signals[df_signals['Señal'].str.contains("BUY|SELL")]
                
                for ticker, row in signals_to_inject.iterrows():
                    u_id = uuid.uuid4()
                    action = "BUY" if "BUY" in row['Señal'] else "SELL"
                    qty = float(row['Qty'])
                    rat = f"Fase: {row['Fase']} | Trend: {float(row['Tendencia']):.3f} | Vol: {row['Vol_Neto']}"
                    
                    con.execute(
                        INSERT INTO quant_core.trade_signals 
                        (signal_id, ticker, action, order_qty, status, rationale, session_uid, strategy_name)
                        VALUES (?, ?, ?, ?, 'PENDING_HITL', ?, 'manual_script', 'overnight_squeeze')
                    , (u_id, ticker, action, qty, rat))
                
                con.close()
                print(f"✅ Señales inyectadas exitosamente.")
            except Exception as e:
                print(f"❌ Error DuckDB: {e}")

        # --- ACTIVACIÓN DE TELEMETRÍA VISUAL ---
        #plot_thermodynamic_scatter(df_signals.reset_index())
        plot_thermodynamic_evolution(df_signals.reset_index())
    else:
        print("❌ No se generaron datos.")

def main():
    print("🌊 Iniciando Escáner de Dinámica de Fluidos Multi-Activo...")
    
    # 1. Ingesta de Capital Real
    equity, err = fetch_ibkr_total_equity_numeric()
    if equity is None:
        print(f"⚠️ Advertencia: No se pudo conectar a IBKR. Usando capital simulado.")
        equity = 10000.0
    else:
        print(f"✅ Equity detectado: ${equity:,.2f} USD")

    tickers = get_portfolio_tickers()
    bogota_tz = pytz.timezone('America/Bogota')
    ny_tz = pytz.timezone('America/New_York')
    
    all_evolutions = {} # Para el gráfico de estelas
    latest_signals = [] # Para la tabla e inyección
    
    print("\n🔍 Analizando termodinámica y trayectoria de activos...")
    for ticker in tickers:
        try:
            # Descarga de datos específica para el ticker
            df = yf.download(ticker, period=DIAS_HISTORIA, interval="5m", progress=False)
            if df.empty: continue
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            # Localización temporal
            if df.index.tz is None: df.index = df.index.tz_localize('UTC')
            df.index = df.index.tz_convert(bogota_tz)
            
            # Purificación
            df['Kalman'] = apply_kalman_filter(df['Close'])
            
            # Aislamiento de hoy
            last_day = df.index[-1].date()
            df_today = df[df.index.date == last_day].copy()
            
            # 2. Calcular Evolución (Estela)
            evolution = analyze_ticker_evolution(ticker, df_today, equity, steps=6)
            if evolution:
                all_evolutions[ticker] = evolution
                
                # 3. Extraer el estado actual (último paso de la evolución)
                current_state = evolution[-1]
                
                # Determinar señal para la tabla (MOC Gate simplificado)
                # Nota: Aquí puedes re-integrar la lógica de MOC si es necesario
                fase = "GAS" if current_state['Vol_Neto'] > 0 and current_state['Tendencia'] > 0 else \
                       "PLASMA" if current_state['Vol_Neto'] < 0 and current_state['Tendencia'] < 0 else "SÓLIDA"
                
                signal = "BUY" if fase == "GAS" else "SELL" if fase == "PLASMA" else "HOLD"
                
                latest_signals.append({
                    "Ticker": ticker,
                    "Señal": signal,
                    "Fase": fase,
                    "Qty": int((equity * RIESGO_CAPITAL_PCT) // current_state['Precio']) if signal != "HOLD" else 0,
                    "Precio": current_state['Precio'],
                    "Tendencia": current_state['Tendencia'],
                    "Vol_Neto": current_state['Vol_Neto']
                })
                
                icon = "🔥" if signal == "BUY" else "🧊" if signal == "SELL" else "⚖️ "
                print(f"  {icon} {ticker:<5} | Fase: {fase:<6} | Trayectoria OK")

        except Exception as e:
            print(f"  ❌ {ticker:<5} | Error: {str(e)}")

    # --- REPORTE Y GRÁFICO ---
    df_signals = pd.DataFrame(latest_signals)
    if not df_signals.empty:
        df_signals.set_index('Ticker', inplace=True)
        print("\n" + "="*70)
        print("   ESTADO ACTUAL DEL FLUIDO (LATEST TICK)")
        print("="*70)
        print(df_signals[['Señal', 'Fase', 'Qty', 'Precio', 'Tendencia', 'Vol_Neto']])
        print("="*70)

        # Inyección a DuckDB (Opcional, igual que antes)
        db_path = os.environ.get("DUCKCLAW_QUANT_SCRIPT_DB")
        if db_path and os.path.exists(db_path):
            try:
                con = duckdb.connect(db_path, read_only=False)
                for ticker, row in df_signals[df_signals['Señal'].str.contains("BUY|SELL")].iterrows():
                    con.execute("INSERT INTO quant_core.trade_signals (signal_id, ticker, action, order_qty, status, rationale, session_uid, strategy_name) VALUES (?, ?, ?, ?, 'PENDING_HITL', ?, 'manual_script', 'overnight_squeeze')", 
                                (str(uuid.uuid4()), ticker, row['Señal'], float(row['Qty']), f"Fase: {row['Fase']} | Trend: {row['Tendencia']:.3f}",))
                con.close()
                print("💾 Ledger actualizado.")
            except Exception as e: print(f"❌ Error DB: {e}")

        # 4. Visualización de Evolución
        #plot_thermodynamic_evolution(all_evolutions)
        plot_thermodynamic_polar(all_evolutions)
    else:
        print("❌ No se generaron datos suficientes.")

if __name__ == "__main__":
    main()
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