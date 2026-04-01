"""
Validación anti-alucinación de precios: comparar cifras del texto con último close en quant_core.ohlcv_data.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional, Tuple

_TICKER_PAT = re.compile(r"\b([A-Z]{1,5})\b")
# Cotización probable: decimal con al menos 2 dígitos fraccionarios o con símbolo $
_PRICE_PAT = re.compile(r"(?:\$\s*)?(\d{1,6}\.\d{2,6})\b")
_MAX_DRIFT = 0.001  # 0.1 %


def spec_is_finanz_quant(spec: Any) -> bool:
    if (getattr(spec, "logical_worker_id", None) or spec.worker_id or "").strip().lower() != "finanz":
        return False
    qc = getattr(spec, "quant_config", None)
    if not isinstance(qc, dict):
        return False
    return bool(qc.get("enabled"))


def _last_close(db: Any, ticker: str) -> Optional[float]:
    try:
        t = "".join(c for c in (ticker or "").upper() if c.isalnum())
        if not t or len(t) > 12:
            return None
        raw = db.query(
            f"SELECT close FROM quant_core.ohlcv_data WHERE UPPER(ticker) = '{t}' "
            "ORDER BY timestamp DESC LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else raw
        if not rows or not isinstance(rows, list):
            return None
        c = rows[0].get("close") if isinstance(rows[0], dict) else None
        if c is None:
            return None
        return float(str(c).replace(",", ""))
    except Exception:
        return None


def _known_tickers(db: Any) -> set[str]:
    try:
        raw = db.query(
            "SELECT DISTINCT UPPER(ticker) AS t FROM quant_core.ohlcv_data LIMIT 500"
        )
        rows = json.loads(raw) if isinstance(raw, str) else raw
        if not rows or not isinstance(rows, list):
            return set()
        out: set[str] = set()
        for row in rows:
            if isinstance(row, dict):
                t = row.get("t") or row.get("ticker")
                if t:
                    out.add(str(t).strip().upper())
        return out
    except Exception:
        return set()


def quant_reply_price_audit(db: Any, spec: Any, reply: str) -> Tuple[str, Optional[str]]:
    """
    Si el texto cita un ticker con OHLCV y un precio numérico incompatible (>0.1%) con último close,
    sustituye por mensaje de cumplimiento.
    """
    if not spec_is_finanz_quant(spec):
        return reply, None
    text = (reply or "").strip()
    if not text:
        return reply, None

    known = _known_tickers(db)
    if not known:
        return reply, None

    mentioned = {m.group(1) for m in _TICKER_PAT.finditer(text) if m.group(1) in known}
    if len(mentioned) != 1:
        return reply, None

    sym = next(iter(mentioned))
    close = _last_close(db, sym)
    if close is None or close <= 0:
        return reply, None

    prices = [float(x) for x in _PRICE_PAT.findall(text)]
    if not prices:
        return reply, None

    for p in prices:
        if abs(p - close) / close > _MAX_DRIFT:
            err = f"precio {p} vs último close {close:.6f} ({sym})"
            return (
                (
                    "La respuesta fue ajustada: un precio citado no coincide (>0.1%) con la última "
                    f"vela en quant_core para {sym} (close ~ {close:.4f}). Usa read_sql o "
                    "fetch_market_data antes de citar cotizaciones actuales."
                ),
                err,
            )
    return reply, None
