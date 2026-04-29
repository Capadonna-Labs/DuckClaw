import yfinance as yf
import pandas as pd
import numpy as np
import json
import seaborn as sns
import matplotlib.pyplot as plt
from scipy.cluster.hierarchy import linkage, dendrogram, leaves_list
from scipy.spatial.distance import squareform

# --- CONFIGURACIÓN DEL ALQUIMISTA ---
TICKERS = ["META", "SPY", "TLT", "GLD", "SHY", "IEF", "XLU"]
PERIODO = "1y"
REBALANCE_THRESHOLD = 0.03
MAX_WEIGHT = 0.35 

def apply_kalman_filter(series):
    """
    Purificación de señal: Filtro de Kalman para estimar el estado real del precio.
    Reduce la viscosidad del ruido sin introducir el lag de una media móvil.
    """
    z = series.values
    n_iter = len(z)
    sz = (n_iter,)
    
    # Parámetros del Filtro (Ajuste de Sensibilidad)
    Q = 1e-5 # Varianza del proceso (confianza en el modelo)
    R = 0.01 # Varianza de la medición (confianza en el dato ruidoso)
    
    xhat = np.zeros(sz)      # Estimación a posteriori del estado
    P = np.zeros(sz)         # Estimación a posteriori del error
    xhatminus = np.zeros(sz) # Estimación a priori del estado
    Pminus = np.zeros(sz)    # Estimación a priori del error
    K = np.zeros(sz)         # Ganancia de Kalman
    
    # Valores iniciales
    xhat[0] = z[0]
    P[0] = 1.0
    
    for k in range(1, n_iter):
        # Predicción
        xhatminus[k] = xhat[k-1]
        Pminus[k] = P[k-1] + Q
        
        # Actualización
        K[k] = Pminus[k] / (Pminus[k] + R)
        xhat[k] = xhatminus[k] + K[k] * (z[k] - xhatminus[k])
        P[k] = (1 - K[k]) * Pminus[k]
        
    return pd.Series(xhat, index=series.index)

def apply_weight_constraints(weights, max_weight):
    w = weights.copy()
    if any(w > max_weight):
        while any(w > max_weight + 1e-6):
            excess = w[w > max_weight] - max_weight
            total_excess = excess.sum()
            w[w > max_weight] = max_weight
            not_capped = w < max_weight
            w[not_capped] += total_excess * (w[not_capped] / w[not_capped].sum())
    return w

def get_hrp_weights(returns_df):
    corr = returns_df.corr()
    cov = returns_df.cov()
    dist = np.sqrt(np.clip((1.0 - corr.values) / 2.0, 0.0, 1.0))
    link = linkage(squareform(dist, checks=False), method="single")
    sort_indices = leaves_list(link)
    sorted_tickers = [corr.columns[i] for i in sort_indices]

    def get_cluster_var(cov_mat, cluster_items):
        c = cov_mat.loc[cluster_items, cluster_items]
        inv_diag = 1.0 / np.diag(c.values)
        w = inv_diag / inv_diag.sum()
        return float(np.dot(w, np.dot(c.values, w)))

    weights = pd.Series(1.0, index=sorted_tickers)
    clusters = [sorted_tickers]
    while clusters:
        new_clusters = []
        for cluster in clusters:
            if len(cluster) <= 1: continue
            split = len(cluster) // 2
            c1, c2 = cluster[:split], cluster[split:]
            v1, v2 = get_cluster_var(cov, c1), get_cluster_var(cov, c2)
            alpha = 1.0 - v1 / (v1 + v2)
            weights[c1] *= alpha
            weights[c2] *= 1.0 - alpha
            new_clusters.extend([c1, c2])
        clusters = new_clusters
    
    constrained_weights = apply_weight_constraints(weights, MAX_WEIGHT)
    return weights, constrained_weights, link, sorted_tickers

def main():
    print(f"🧪 Inyectando masa de datos y aplicando Filtro de Kalman...")
    data = yf.download(TICKERS, period=PERIODO)["Close"]
    
    # 1. Purificación vía Kalman
    kalman_data = data.apply(apply_kalman_filter)
    
    # 2. Cálculo de retornos sobre señal purificada
    returns = kalman_data.pct_change().dropna()
    
    # 3. Ejecución del Reactor HRP
    raw_w, final_w, link, ordered_tickers = get_hrp_weights(returns)
    
    # --- REPORTE TÉCNICO ---
    print("\n" + "="*45)
    print(f"{'TICKER':<10} | {'HRP+KALMAN':<12} | {'CONSTRUIDO (CAP)':<15}")
    print("-" * 45)
    for t in final_w.sort_values(ascending=False).index:
        print(f"{t:<10} | {raw_w[t]:>10.2%} | {final_w[t]:>12.2%}")
    print("="*45)

    # --- VISUALIZACIÓN ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 7))
    
    # Comparativa de Señal (Ejemplo con SPY)
    ax1.plot(data['SPY'] / data['SPY'].iloc[0], label='Precio Raw (Ruidoso)', alpha=0.4)
    ax1.plot(kalman_data['SPY'] / kalman_data['SPY'].iloc[0], label='Precio Kalman (Purificado)', color='red')
    ax1.set_title("Efecto Kalman: Purificación de Señal (SPY)")
    ax1.legend()
    
    # Comparativa de Pesos
    comparison = pd.DataFrame({'HRP Puro': raw_w, 'HRP Constrained': final_w})
    comparison.plot(kind='bar', ax=ax2)
    ax2.set_title("Distribución de Masa Final")
    ax2.set_ylabel("Peso %")

    print("\n📊 Telemetría visual lista. El Filtro de Kalman ha estabilizado el reactor.")
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()