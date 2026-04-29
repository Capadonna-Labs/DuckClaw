import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import matplotlib.dates as mdates
import pytz

# --- CONFIGURACIÓN DEL ALQUIMISTA ---
TICKER = "SPY"
# Usamos 2 días de datos en velas de 1 minuto para que el Filtro de Kalman "caliente"
DIAS_HISTORIA = "2d" 

def apply_kalman_filter(series):
    """Filtro de Kalman 1D para purificar la señal de precio (elimina ruido HFT)"""
    z = series.values
    n_iter = len(z)
    sz = (n_iter,)
    
    Q = 1e-5  # Varianza del proceso
    R = 0.01  # Varianza de la medición
    
    xhat = np.zeros(sz)
    P = np.zeros(sz)
    xhatminus = np.zeros(sz)
    Pminus = np.zeros(sz)
    K = np.zeros(sz)
    
    xhat[0] = z[0]
    P[0] = 1.0
    
    for k in range(1, n_iter):
        xhatminus[k] = xhat[k-1]
        Pminus[k] = P[k-1] + Q
        K[k] = Pminus[k] / (Pminus[k] + R)
        xhat[k] = xhatminus[k] + K[k] * (z[k] - xhatminus[k])
        P[k] = (1 - K[k]) * Pminus[k]
        
    return pd.Series(xhat, index=series.index)

def main():
    """
    print(f"🌊 Iniciando Reactor Overnight Gap Squeeze para {TICKER}...")
    
    # 1. Ingesta de Masa (Velas de 1 minuto)
    try:
        df = yf.download(TICKER, period=DIAS_HISTORIA, interval="1m", progress=False)
        if df.empty:
            print("❌ Error: No se obtuvieron datos.")
            return
    except Exception as e:
        print(f"❌ Error de Ingesta: {e}")
        return

    # Aplanar multi-index si yfinance lo devuelve
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # 2. Purificación de la Señal (Kalman)
    df['Kalman'] = apply_kalman_filter(df['Close'])
    
    # 3. Aislamiento de la Última Sesión y la Última Hora
    # Extraemos el último día disponible
    last_day = df.index[-1].date()
    df_today = df[df.index.date == last_day].copy()
    
    # Extraemos los últimos 30 minutos (Proxy de MOC Imbalance)
    # Asumimos que el mercado cierra a las 16:00 EST. 
    df_end_of_day = df_today.iloc[-30:].copy()
    
    # 4. Cálculo de Termodinámica (Presión Institucional)
    # Calculamos el Delta de Kalman (Dirección real del fluido)
    df_end_of_day['Kalman_Delta'] = df_end_of_day['Kalman'].diff()
    
    # Volumen Direccional (Masa * Dirección)
    df_end_of_day['Net_Volume'] = np.where(df_end_of_day['Close'] > df_end_of_day['Open'], 
                                           df_end_of_day['Volume'], 
                                           -df_end_of_day['Volume'])
    
    cumulative_net_volume = df_end_of_day['Net_Volume'].sum()
    price_trend = df_end_of_day['Kalman'].iloc[-1] - df_end_of_day['Kalman'].iloc[0]
    
    # 5. Veredicto del Fluido
    fase = "SÓLIDA (Rango)"
    signal = "HOLD"
    
    if cumulative_net_volume > 0 and price_trend > 0:
        fase = "GAS (Expansión Alcista)"
        signal = "BUY (Overnight Squeeze)"
    elif cumulative_net_volume < 0 and price_trend < 0:
        fase = "PLASMA (Contracción Severa)"
        signal = "SELL / SHORT"

    # --- REPORTE TÉCNICO ---
    print("\n" + "="*50)
    print(f"   TELEMETRÍA DE CIERRE (MOC PROXY) - {TICKER}")
    print("="*50)
    print(f"Fecha de análisis : {last_day}")
    print(f"Tendencia Kalman  : {'Alcista 🟢' if price_trend > 0 else 'Bajista 🔴'} ({price_trend:.2f} pts)")
    print(f"Masa Neta (30m)   : {cumulative_net_volume:,.0f} shares")
    print(f"Estado del Fluido : {fase}")
    print("-" * 50)
    print(f"🔥 SEÑAL PROPUESTA : {signal}")
    print("="*50)

    # --- VISUALIZACIÓN ---
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={'height_ratios': [3, 1]})
    
    # Gráfico de Precio vs Kalman (Último día)
    ax1.plot(df_today.index, df_today['Close'], label='Precio 1m (Ruido)', color='lightgray', alpha=0.7)
    ax1.plot(df_today.index, df_today['Kalman'], label='Filtro Kalman (Señal Pura)', color='blue', linewidth=2)
    
    # Resaltar los últimos 30 minutos
    ax1.axvspan(df_end_of_day.index[0], df_end_of_day.index[-1], color='yellow', alpha=0.2, label='Ventana MOC (30m)')
    ax1.set_title(f"Dinámica de Fluidos Intradía - {TICKER}")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Gráfico de Volumen Direccional (Últimos 30 min)
    colors =['green' if v > 0 else 'red' for v in df_end_of_day['Net_Volume']]
    # ax2.bar(df_end_of_day.index, df_end_of_day['Volume'], color=colors, alpha=0.7)
    # width = 1 minuto / (24 horas * 60 minutos)
    ax2.bar(df_end_of_day.index, df_end_of_day['Volume'], color=colors, alpha=0.7, width=1/(24*60))
    ax2.set_title("Presión de Masa (Volumen Direccional Últimos 30m)")
    ax2.grid(True, alpha=0.3)

    # Formateo del Eje X para mostrar Fecha y Hora
    date_format = mdates.DateFormatter('%Y-%m-%d %H:%M')
    ax1.xaxis.set_major_formatter(date_format)
    ax2.xaxis.set_major_formatter(date_format)
    
    # Rotar las etiquetas para que no se superpongan
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')

    plt.tight_layout()
    print("\n📊 Generando telemetría visual... (Cierra la ventana para finalizar)")
    plt.show()
    """
    print(f"🌊 Iniciando Reactor de Dinámica Intradía para {TICKER}...")
    
    try:
        df = yf.download(TICKER, period="5d", interval="5m", progress=False)
        if df.empty:
            print("❌ Error: No se obtuvieron datos.")
            return
    except Exception as e:
        print(f"❌ Error de Ingesta: {e}")
        return

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # 1. Manejo de Zonas Horarias
    if df.index.tz is None:
        df.index = df.index.tz_localize('UTC')
    
    # Convertir a hora de Bogotá para visualización y reporte
    bogota_tz = pytz.timezone('America/Bogota')
    df.index = df.index.tz_convert(bogota_tz)

    # 2. Purificación de la Señal (Kalman)
    df['Kalman'] = apply_kalman_filter(df['Close'])
    
    # 3. Aislamiento de la Última Sesión
    last_day = df.index[-1].date()
    df_today = df[df.index.date == last_day].copy()
    
    if df_today.empty or len(df_today) < 2:
        print("❌ Error: No hay suficientes datos en la sesión actual.")
        return

    # --- CONCIENCIA TEMPORAL (Ajustada a Bogotá) ---
    # Wall Street cierra a las 16:00 EST. 
    # En abril (horario de verano en US), 16:00 EDT = 15:00 Bogotá.
    # En invierno (EST), 16:00 EST = 16:00 Bogotá.
    # Para hacerlo dinámico, calculamos el cierre de NY y lo convertimos a Bogotá.
    
    ny_tz = pytz.timezone('America/New_York')
    last_timestamp_ny = df_today.index[-1].astimezone(ny_tz)
    
    market_close_ny = last_timestamp_ny.replace(hour=16, minute=0, second=0, microsecond=0)
    moc_start_ny = last_timestamp_ny.replace(hour=15, minute=30, second=0, microsecond=0)
    
    # Convertimos esos hitos a la zona horaria de Bogotá para comparar con nuestro índice
    market_close = market_close_ny.astimezone(bogota_tz)
    moc_start = moc_start_ny.astimezone(bogota_tz)
    
    last_timestamp = df_today.index[-1]
    
    # Determinar la fase de la sesión
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

    # --- CÁLCULO DE TERMODINÁMICA ---
    df_analysis['Kalman_Delta'] = df_analysis['Kalman'].diff()
    df_analysis['Net_Volume'] = np.where(df_analysis['Close'] > df_analysis['Open'], 
                                           df_analysis['Volume'], 
                                           -df_analysis['Volume'])
    
    cumulative_net_volume = df_analysis['Net_Volume'].sum()
    price_trend = df_analysis['Kalman'].iloc[-1] - df_analysis['Kalman'].iloc[0]
    
    fase_fluido = "SÓLIDA (Rango)"
    signal = "HOLD"
    
    if cumulative_net_volume > 0 and price_trend > 0:
        fase_fluido = "GAS (Expansión Alcista)"
        signal = "BUY (Overnight Squeeze)" if fase_sesion == "MOC (Cierre Institucional)" else "BUY (Momentum Intradía)"
    elif cumulative_net_volume < 0 and price_trend < 0:
        fase_fluido = "PLASMA (Contracción Severa)"
        signal = "SELL / SHORT"

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

    # Formateo del Eje X en hora de Bogotá
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