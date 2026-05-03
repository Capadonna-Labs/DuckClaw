# Snippet sandbox: PortfolioAnalysis (ML4T diagnostic) desde retornos diarios YA calculados en el host.
#
# Obligatorio antes de ejecutar:
# - Sustituir la lista placeholder `rets` por floats (p. ej. retornos diarios EW a partir de OHLCV
#   de `fetch_market_data` / `fetch_ib_gateway_ohlcv` del mismo turno).
#
# Sin ml4t-data ni red dentro del sandbox Quant (política default deny_network).
import json

import numpy as np
import pandas as pd
from ml4t.diagnostic.evaluation import PortfolioAnalysis

rets: list[float] = []  # noqa: ERA001 — el modelo debe reemplazar antes de ejecutar

def main() -> None:
    s = pd.Series([float(x) for x in rets], dtype=float)
    s = s.replace([np.inf, -np.inf], np.nan).dropna()
    if s.shape[0] > 10000:
        s = s.iloc[-10000:]
    if s.shape[0] < 21:
        raise SystemExit(json.dumps({"ok": False, "error": "rets needs >=21 points"}, ensure_ascii=False))
    m = PortfolioAnalysis(s).compute_summary_stats()
    out = {k: float(v) if hasattr(v, "item") else v for k, v in vars(m).items() if not k.startswith("_")}
    print(json.dumps({"ok": True, "n": int(s.shape[0]), "ml4t_metrics": out}, ensure_ascii=False, default=str))

if __name__ == "__main__":
    main()