"""
Validación anti-alucinación de precios: comparar cifras del texto con último close en quant_core.ohlcv_data.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional, Tuple
from langchain_core.messages import ToolMessage

_TICKER_PAT = re.compile(r"\b([A-Z]{1,5})\b")
# Cotización probable: decimal con al menos 2 dígitos fraccionarios o con símbolo $
_PRICE_PAT = re.compile(r"(?:\$\s*)?(\d{1,6}\.\d{2,6})\b")
_MAX_DRIFT = 0.001  # 0.1 %
_VLM_MARKER = "VLM_CONTEXT"
_EVIDENCE_TOOLS = {"fetch_market_data", "fetch_lake_ohlcv", "read_sql"}

_NUMERIC_VERIFY_STATUSES = frozenset({"verified", "mismatch", "no_evidence"})


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


def _tool_message_satisfies_visual_evidence(m: ToolMessage) -> bool:
    nm = str(getattr(m, "name", "") or "").strip()
    content = str(getattr(m, "content", "") or "")
    low = content.lower()
    if nm in _EVIDENCE_TOOLS and "error" not in low:
        return True
    if nm == "verify_visual_claim":
        if "error" in low:
            return False
        try:
            data = json.loads(content)
            if isinstance(data, dict) and data.get("status") in _NUMERIC_VERIFY_STATUSES:
                return True
        except (json.JSONDecodeError, TypeError):
            pass
    return False


def enforce_visual_evidence_rule(
    *,
    incoming: str,
    messages: list[Any],
    reply: str,
    db: Any = None,
    spec: Any = None,
) -> Tuple[str, Optional[str]]:
    """
    Si hay contexto visual inyectado, exige evidencia tool-call en el mismo turno antes de citar cifras
    que parezcan cotizaciones. Para capturas de noticias (sin ticker en quant_core.ohlcv_data en el texto),
    no bloquea: evita falsos positivos con montos tipo “1,75 billones”.
    """
    inc = (incoming or "").strip()
    text = (reply or "").strip()
    if not inc or _VLM_MARKER not in inc:
        return reply, None
    if not _PRICE_PAT.search(text):
        return reply, None

    if (
        db is not None
        and spec is not None
        and spec_is_finanz_quant(spec)
    ):
        known = _known_tickers(db)
        if not known:
            return reply, None
        mentioned = {m.group(1) for m in _TICKER_PAT.finditer(text) if m.group(1) in known}
        if not mentioned:
            return reply, None

    for m in messages or []:
        if isinstance(m, ToolMessage) and _tool_message_satisfies_visual_evidence(m):
            return reply, None
    return (
        "❌ Regla de Evidencia Única: detecté contexto visual y cifras de mercado sin tool call válido en este turno. "
        "Ejecuta fetch_market_data/fetch_lake_ohlcv o read_sql primero y luego recalculo.",
        "missing_tool_evidence_for_vlm_claim",
    )
