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
# Por debajo de este factor del menor ancla OHLC, un decimal no se trata como cotización accionario
# (runtime: métricas CFD tipo "densidad 0.000152" con SPY ~657).
_MIN_QUOTE_VS_MIN_ANCHOR_FRAC = 0.01
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


def _parse_ohlc_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        x = float(str(val).replace(",", "").strip())
        if x <= 0 or x > 1e9:
            return None
        return x
    except (TypeError, ValueError):
        return None


def _read_sql_payload_symbol_scope(rows: list[Any], sym_u: str) -> bool:
    """
    True si las filas JSON de read_sql pueden atribuirse a sym_u: todas sin ticker,
    o todas con ticker compatible con sym_u (ninguna otra acción mezclada).
    """
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        tk = row.get("ticker") or row.get("symbol") or row.get("TICKER") or row.get("Symbol")
        if tk:
            seen.add(str(tk).strip().upper())
    if not seen:
        return True
    return sym_u in seen and seen <= {sym_u}


def _aggregate_ohlc_fields_from_row(row: dict[str, Any]) -> list[float]:
    """Columnas agregadas típicas de read_sql (MAX/MIN) como anclas."""
    keys = (
        "max_close",
        "min_close",
        "max_open",
        "min_open",
        "max_high",
        "min_high",
        "max_low",
        "min_low",
    )
    vals: list[float] = []
    for k in keys:
        f = _parse_ohlc_float(row.get(k))
        if f is not None:
            vals.append(f)
    return vals


def _ohlc_numbers_from_messages_for_ticker(messages: list[Any], sym: str) -> set[float]:
    """
    Números OHLC presentes en salidas de herramientas del mismo turno para ``sym``.
    Evita falsos positivos cuando el modelo resume varias velas (p. ej. close histórico 658.53
    vs último close 657.25).

    Incluye: filas sin columna ticker (read_sql frecuente), agregados max_close/min_close,
    y evidencia con ticker explícito.
    """
    sym_u = (sym or "").strip().upper()
    out: set[float] = set()
    if not sym_u or not messages:
        return out
    ohlc_keys = ("open", "high", "low", "close")
    max_rows = 400

    for m in messages:
        name, body = "", ""
        if isinstance(m, dict):
            role = (m.get("role") or m.get("type") or "").lower()
            if role not in ("tool", "toolmessage"):
                continue
            name = str(m.get("name") or "")
            c = m.get("content")
            body = str(c) if c is not None else ""
        else:
            if type(m).__name__ != "ToolMessage" and getattr(m, "type", None) != "tool":
                continue
            name = str(getattr(m, "name", "") or "")
            body = str(getattr(m, "content", "") or "")
        name = name.strip()
        if name not in ("read_sql", "fetch_market_data", "fetch_lake_ohlcv"):
            continue
        body = body.strip()
        if not body:
            continue
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and data.get("error") is not None:
            continue

        rows: list[Any] = []
        if isinstance(data, list):
            rows = data[:max_rows]
        elif isinstance(data, dict):
            nested = data.get("data")
            if isinstance(nested, list):
                rows = nested[:max_rows]

        scope_ok = _read_sql_payload_symbol_scope(rows, sym_u) if name == "read_sql" else True

        for row in rows:
            if not isinstance(row, dict):
                continue
            tk = row.get("ticker") or row.get("symbol") or row.get("TICKER") or row.get("Symbol")
            tk_u = str(tk).strip().upper() if tk else ""
            row_for_sym = (tk_u == sym_u) or (not tk_u and scope_ok and name == "read_sql")
            if not row_for_sym:
                continue
            for k in ohlc_keys:
                f = _parse_ohlc_float(row.get(k))
                if f is not None:
                    out.add(f)
            if name == "read_sql":
                for f in _aggregate_ohlc_fields_from_row(row):
                    out.add(f)
    return out


def _price_matches_any_anchor(price: float, anchors: set[float]) -> bool:
    for a in anchors:
        if a > 0 and abs(price - a) / a <= _MAX_DRIFT:
            return True
    return False


def _below_plausible_share_quote_vs_anchors(price: float, anchors: set[float]) -> bool:
    pos = [a for a in anchors if a > 0]
    if not pos or price <= 0:
        return False
    return price < min(pos) * _MIN_QUOTE_VS_MIN_ANCHOR_FRAC


def _price_in_non_market_context(text: str, match_start: int, match_end: int, *, window: int = 140) -> bool:
    """
    Evita validar montos de cuentas/broker como cotización del único ticker OHLC citado.
    Evidencia runtime: 995.54 (efectivo IBKR) junto a SPY en el mismo reply disparaba el auditor.
    """
    lo = max(0, match_start - window)
    hi = min(len(text), match_end + window)
    chunk = text[lo:hi].lower()
    needles = (
        "ibkr",
        "interactive brokers",
        "broker:",
        "broker (",
        "gateway",
        "cuentas locales",
        "cuenta ibkr",
        "bancolombia",
        "nequi",
        "global66",
        "tarjeta cívica",
        "tarjeta civica",
        "nu:",
        "liquidez total",
        "total cuentas",
        "saldo:",
        "usd efectivo",
        "efectivo ($",
        "resumen de cuentas",
        "estado actual de cuentas",
    )
    return any(n in chunk for n in needles)


def _price_in_vix_or_index_context(
    text: str, match_start: int, match_end: int, *, window: int = 120
) -> bool:
    """
    VIX y niveles de índices (p. ej. S&P 500 ~6500) no son cotización del único ticker
    conocido SPY en quant_core; evidencia PM2: 24.50 validado contra SPY last≈656.
    """
    lo = max(0, match_start - window)
    hi = min(len(text), match_end + window)
    chunk = text[lo:hi].lower()
    needles = (
        "vix",
        "volatility index",
        "índice vix",
        "indice vix",
        "volatilidad implícita",
        "volatilidad (vix",
        "s&p 500",
        "s&p500",
        "sp500",
        "dow jones",
        "promedio industrial",
        "nasdaq composite",
    )
    return any(n in chunk for n in needles)


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


def quant_reply_price_audit(
    db: Any,
    spec: Any,
    reply: str,
    messages: Optional[list[Any]] = None,
) -> Tuple[str, Optional[str]]:
    """
    Si el texto cita un ticker con OHLCV y un precio numérico incompatible (>0.1%) con **cualquier**
    ancla válida (último close en DB u OHLC de evidencia de read_sql/fetch en el mismo turno),
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

    evidence = _ohlc_numbers_from_messages_for_ticker(list(messages or []), sym)
    anchors: set[float] = {close} | evidence

    quote_candidates: list[float] = []
    for m in _PRICE_PAT.finditer(text):
        p = float(m.group(1))
        if _price_in_non_market_context(text, m.start(), m.end()):
            continue
        if _price_in_vix_or_index_context(text, m.start(), m.end()):
            continue
        if _below_plausible_share_quote_vs_anchors(p, anchors):
            continue
        quote_candidates.append(p)

    if not quote_candidates:
        return reply, None

    for p in quote_candidates:
        if not _price_matches_any_anchor(p, anchors):
            err = f"precio {p} no alineado con último close ni OHLC de tools del turno ({sym}, last≈{close:.4f})"
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
