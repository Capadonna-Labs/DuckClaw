"""
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
PERIODO = "1y"  # Masa de datos de 1 año para estabilidad térmica
REBALANCE_THRESHOLD = 0.03  # 3% de deriva para ignición

def get_hrp_weights(returns_df):
    
    Implementación de Hierarchical Risk Parity (HRP)
    Mapea la viscosidad (correlación) y distribuye la masa (capital).
    
    corr = returns_df.corr()
    cov = returns_df.cov()
    
    # 1. Cálculo de Distancia y Linkage (Clustering Jerárquico)
    # d = sqrt(0.5 * (1 - rho))
    dist = np.sqrt(np.clip((1.0 - corr.values) / 2.0, 0.0, 1.0))
    link = linkage(squareform(dist, checks=False), method="single")

    # 2. Quasi-Diagonalización (Ordenamiento Topológico)
    sort_indices = leaves_list(link)
    sorted_tickers = [corr.columns[i] for i in sort_indices]

    # 3. Bisección Recursiva (Asignación de Masa por Temperatura)
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
            
            # División del clúster en dos cámaras de presión
            split = len(cluster) // 2
            c1, c2 = cluster[:split], cluster[split:]
            
            # Cálculo de varianza (Temperatura) de cada cámara
            v1, v2 = get_cluster_var(cov, c1), get_cluster_var(cov, c2)
            
            # Factor de asignación (Alpha)
            alpha = 1.0 - v1 / (v1 + v2)
            
            # Transmisión de masa
            weights[c1] *= alpha
            weights[c2] *= 1.0 - alpha
            new_clusters.extend([c1, c2])
        clusters = new_clusters
    
    return weights, link, sorted_tickers

def main():
    print(f"🧪 Inyectando masa de datos para: {TICKERS}...")
    try:
        data = yf.download(TICKERS, period=PERIODO)["Close"]
    except Exception as e:
        print(f"🔴 Error de Ingesta: {e}")
        return

    # Limpieza de fluido (Cavitación de datos)
    returns = data.ffill().bfill().pct_change().dropna()
    
    # Ejecución del Reactor
    target_weights, link, ordered_tickers = get_hrp_weights(returns)
    
    # --- REPORTE TÉCNICO ---
    print("\n" + "="*30)
    print("   PESOS OBJETIVO (HRP)")
    print("="*30)
    report = target_weights.sort_values(ascending=False)
    for t, w in report.items():
        print(f"{t:6}: {w:>7.2%}")
    print("="*30)

    # --- VISUALIZACIÓN DE TOPOLOGÍA ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 7))

    # 1. Dendrograma (Árbol de Viscosidad)
    dendrogram(link, labels=returns.columns, ax=ax1, leaf_rotation=90)
    ax1.set_title("Jerarquía de Riesgo (Dendrograma)")
    ax1.set_ylabel("Distancia Estocástica")

    # 2. Mapa de Calor Quasi-Diagonalizado
    sorted_corr = returns[ordered_tickers].corr()
    sns.heatmap(sorted_corr, annot=True, fmt=".2f", cmap="YlOrRd", ax=ax2, square=True)
    ax2.set_title("Matriz Quasi-Diagonalizada (Cámaras de Presión)")

    print("\n📊 Generando telemetría visual... (Cierra la ventana para finalizar)")
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()
"""
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
MAX_WEIGHT = 0.35  # 🛡️ Techo de masa: Ningún activo superará el 35%

def apply_weight_constraints(weights, max_weight):
    """Redistribuye el exceso de masa de forma iterativa"""
    w = weights.copy()
    if any(w > max_weight):
        while any(w > max_weight + 1e-6):
            # Identificar exceso
            excess = w[w > max_weight] - max_weight
            total_excess = excess.sum()
            # Topar activos
            w[w > max_weight] = max_weight
            # Redistribuir en los que están por debajo del tope
            not_capped = w < max_weight
            w[not_capped] += total_excess * (w[not_capped] / w[not_capped].sum())
    return w

def get_hrp_weights(returns_df):
    corr = returns_df.corr()
    cov = returns_df.cov()
    
    # 1. Clustering Jerárquico
    dist = np.sqrt(np.clip((1.0 - corr.values) / 2.0, 0.0, 1.0))
    link = linkage(squareform(dist, checks=False), method="single")

    # 2. Quasi-Diagonalización
    sort_indices = leaves_list(link)
    sorted_tickers = [corr.columns[i] for i in sort_indices]

    # 3. Bisección Recursiva
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
    
    # 4. Aplicar Válvula de Restricción
    constrained_weights = apply_weight_constraints(weights, MAX_WEIGHT)
    
    return weights, constrained_weights, link, sorted_tickers

def main():
    print(f"🧪 Inyectando masa de datos para: {TICKERS}...")
    data = yf.download(TICKERS, period=PERIODO)["Close"]
    returns = data.ffill().bfill().pct_change().dropna()
    
    # Ejecución del Reactor
    raw_w, final_w, link, ordered_tickers = get_hrp_weights(returns)
    
    # --- REPORTE TÉCNICO ---
    print("\n" + "="*45)
    print(f"{'TICKER':<10} | {'HRP PURO':<12} | {'CONSTRUIDO (CAP)':<15}")
    print("-" * 45)
    for t in final_w.sort_values(ascending=False).index:
        print(f"{t:<10} | {raw_w[t]:>10.2%} | {final_w[t]:>12.2%}")
    print("="*45)
    print(f"🛡️ Techo de masa aplicado: {MAX_WEIGHT:.0%}")

    # --- VISUALIZACIÓN ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 7))
    dendrogram(link, labels=returns.columns, ax=ax1, leaf_rotation=90)
    ax1.set_title("Jerarquía de Riesgo (Dendrograma)")
    
    # Comparativa de Pesos
    comparison = pd.DataFrame({'HRP Puro': raw_w, 'HRP Constrained': final_w})
    comparison.plot(kind='bar', ax=ax2)
    ax2.set_title("Efecto de la Válvula de Restricción")
    ax2.set_ylabel("Masa (Peso %)")

    print("\n📊 Telemetría visual lista. El fluido se ha redistribuido.")
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()