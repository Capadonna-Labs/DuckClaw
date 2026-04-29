import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import matplotlib.dates as mdates
import pytz
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# 1. Cargar variables de entorno desde el .env en la raíz del proyecto
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# 2. Añadir la raíz del proyecto al path para poder importar duckclaw
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from packages.agents.src.duckclaw.forge.skills.ibkr_bridge import fetch_ibkr_total_equity_numeric

# --- CONFIGURACIÓN DEL ALQUIMISTA ---
TICKER = "SPY"
DIAS_HISTORIA = "5d" 
RIESGO_CAPITAL_PCT = 0.05  # 5% del Equity total para este trade

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

def main():
    print(f"🌊 Iniciando Reactor Overnight Gap Squeeze para {TICKER}...")
    
    # 1. Ingesta de Capital Real (IBKR)
    print("🏦 Consultando Equity en IBKR...")
    equity, err = fetch_ibkr_total_equity_numeric()
    if equity is None:
        print(f"⚠️ Advertencia: No se pudo conectar a IBKR ({err}). Usando capital simulado de $10,000.")
        equity = 10000.0
    else:
        print(f"✅ Equity detectado: ${equity:,.2f} USD")

    # 2. Ingesta de Masa (Mercado)
    try:
        df = yf.download(TICKER, period=DIAS_HISTORIA, interval="5m", progress=False)
        if df.empty:
            print("❌ Error: No se obtuvieron datos de mercado.")
            return
    except Exception as e:
        print(f"❌ Error de Ingesta: {e}")
        return

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    
    bogota_tz = pytz.timezone('America/Bogota')
    df.index = df.index.tz_convert(bogota_tz)

    # 3. Purificación (Kalman)
    df['Kalman'] = apply_kalman_filter(df['Close'])
    
    last_day = df.index[-1].date()
    df_today = df[df.index.date == last_day].copy()
    
    if df_today.empty or len(df_today) < 2:
        print("❌ Error: No hay suficientes datos en la sesión actual.")
        return

    # 4. Conciencia Temporal
    ny_tz = pytz.timezone('America/New_York')
    last_timestamp_ny = df_today.index[-1].astimezone(ny_tz)
    market_close_ny = last_timestamp_ny.replace(hour=16, minute=0, second=0, microsecond=0)
    moc_start_ny = last_timestamp_ny.replace(hour=15, minute=30, second=0, microsecond=0)
    
    market_close = market_close_ny.astimezone(bogota_tz)
    moc_start = moc_start_ny.astimezone(bogota_tz)
    last_timestamp = df_today.index[-1]
    
    if last_timestamp < moc_start:
        fase_sesion = "INTRADÍA (Desarrollo)"
        df_analysis = df_today.iloc[-6:].copy() 
        titulo_ventana = "Últimos 30m (Intradía)"
    elif last_timestamp >= moc_start and last_timestamp <= market_close:
        fase_sesion = "MOC (Cierre Institucional)"
        df_analysis = df_today[df_today.index >= moc_start].copy()
        titulo_ventana = "Ventana MOC"
    else:
        fase_sesion = "POST-MERCADO (Cerrado)"
        df_analysis = df_today[(df_today.index >= moc_start) & (df_today.index <= market_close)].copy()
        titulo_ventana = "Ventana MOC (Cierre)"

    if df_analysis.empty:
        df_analysis = df_today.iloc[-6:].copy()

    # 5. Termodinámica
    df_analysis['Kalman_Delta'] = df_analysis['Kalman'].diff()
    df_analysis['Net_Volume'] = np.where(df_analysis['Close'] > df_analysis['Open'], 
                                           df_analysis['Volume'], 
                                           -df_analysis['Volume'])
    
    cumulative_net_volume = df_analysis['Net_Volume'].sum()
    price_trend = df_analysis['Kalman'].iloc[-1] - df_analysis['Kalman'].iloc[0]
    current_price = df_today['Close'].iloc[-1]
    
    fase_fluido = "SÓLIDA (Rango)"
    signal = "HOLD"
    
    if cumulative_net_volume > 0 and price_trend > 0:
        fase_fluido = "GAS (Expansión Alcista)"
        signal = "BUY (Overnight Squeeze)" if fase_sesion == "MOC (Cierre Institucional)" else "BUY (Momentum Intradía)"
    elif cumulative_net_volume < 0 and price_trend < 0:
        fase_fluido = "PLASMA (Contracción Severa)"
        signal = "SELL / SHORT"

    # 6. Position Sizing (Cálculo de Masa a Inyectar)
    capital_asignado = equity * RIESGO_CAPITAL_PCT
    qty_propuesta = int(capital_asignado // current_price)

    # --- REPORTE TÉCNICO ---
    print("\n" + "="*50)
    print(f"   TELEMETRÍA DE FLUIDO - {TICKER} | Fase: {fase_sesion}")
    print("="*50)
    print(f"Fecha de análisis : {last_day}")
    print(f"Hora del último tick: {last_timestamp.strftime('%H:%M %Z')}")
    print(f"Tendencia Kalman  : {'Alcista 🟢' if price_trend > 0 else 'Bajista 🔴'} ({price_trend:.2f} pts)")
    print(f"Masa Neta ({titulo_ventana}): {cumulative_net_volume:,.0f} shares")
    print(f"Estado del Fluido : {fase_fluido}")
    print("-" * 50)
    print(f"🔥 SEÑAL PROPUESTA : {signal}")
    if signal != "HOLD":
        print(f"💰 Capital Asignado: ${capital_asignado:,.2f} USD ({RIESGO_CAPITAL_PCT*100}%)")
        print(f"📦 Cantidad (Qty)  : {qty_propuesta} unidades a ${current_price:.2f}")
    print("="*50)

    # --- VISUALIZACIÓN ---
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={'height_ratios':[3, 1]})
    
    ax1.plot(df_today.index, df_today['Close'], label='Precio 5m (Ruido)', color='lightgray', alpha=0.7)
    ax1.plot(df_today.index, df_today['Kalman'], label='Filtro Kalman (Señal Pura)', color='blue', linewidth=2)
    
    ax1.axvspan(df_analysis.index[0], df_analysis.index[-1], color='yellow', alpha=0.2, label=titulo_ventana)
    ax1.set_title(f"Dinámica de Fluidos - {TICKER} ({last_day})")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    colors =['green' if v > 0 else 'red' for v in df_analysis['Net_Volume']]
    ax2.bar(df_analysis.index, df_analysis['Volume'], color=colors, alpha=0.7, width=5/(24*60))
    ax2.set_title(f"Presión de Masa ({titulo_ventana})")
    ax2.grid(True, alpha=0.3)

    date_format = mdates.DateFormatter('%H:%M', tz=bogota_tz)
    ax1.xaxis.set_major_formatter(date_format)
    ax2.xaxis.set_major_formatter(date_format)
    
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')

    plt.tight_layout()
    print("\n📊 Generando telemetría visual... (Cierra la ventana para finalizar)")
    plt.show()

if __name__ == "__main__":
    main()