"""
FMP Bridge — dividendos por ticker y calendario global (read-only).

Spec: specs/features/Integración FMP dividendos (read-only).md
Requiere: FMP_API_KEY. Opcional: FMP_API_BASE (default https://financialmodelingprep.com).
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)

_FMP_KEY_ENV = "FMP_API_KEY"
_FMP_BASE_ENV = "FMP_API_BASE"
_FMP_DEFAULT_BASE = "https://financialmodelingprep.com"
_HTTP_TIMEOUT_SEC = 20.0
_MAX_CALENDAR_SPAN_DAYS = 90
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _fmp_api_key() -> str:
    return (os.environ.get(_FMP_KEY_ENV) or "").strip()


def _fmp_base_url() -> str:
    raw = (os.environ.get(_FMP_BASE_ENV) or "").strip().rstrip("/")
    return raw if raw else _FMP_DEFAULT_BASE


def _parse_iso_date(label: str, value: str) -> date:
    s = (value or "").strip()
    if not _DATE_RE.match(s):
        raise ValueError(f"{label} debe ser YYYY-MM-DD (recibido: {value!r}).")
    return datetime.strptime(s, "%Y-%m-%d").date()


def _fmp_get_json(path: str, query: dict[str, str]) -> Any:
    """GET JSON desde FMP. query no debe incluir apikey; se añade aquí."""
    api_key = _fmp_api_key()
    if not api_key:
        raise ValueError("FMP_API_KEY no está configurada. Añádela al entorno del gateway.")

    q = {**query, "apikey": api_key}
    url = f"{_fmp_base_url().rstrip('/')}/{path.lstrip('/')}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SEC) as resp:
            status = getattr(resp, "status", 200)
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        _log.warning("fmp HTTP error path=%s status=%s", path, getattr(e, "code", "?"))
        raise ValueError(f"FMP respondió HTTP {getattr(e, 'code', '?')} para {path}.") from e
    except urllib.error.URLError as e:
        _log.warning("fmp URL error path=%s: %s", path, e)
        raise ValueError(f"No se pudo conectar con FMP: {e}") from e

    if status and status >= 400:
        raise ValueError(f"FMP respondió HTTP {status} para {path}.")

    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        _log.warning("fmp JSON decode path=%s: %s", path, e)
        raise ValueError("FMP devolvió un cuerpo que no es JSON válido.") from e


def _dividend_sort_key(row: dict[str, Any]) -> str:
    for k in ("paymentDate", "date", "recordDate", "declarationDate"):
        v = row.get(k)
        if v:
            return str(v)[:10]
    return ""


def _format_dividend_rows(rows: list[dict[str, Any]], *, title: str, max_rows: int) -> str:
    if not rows:
        return f"{title}: sin filas."
    lines = [title, ""]
    for r in rows[:max_rows]:
        sym = str(r.get("symbol") or r.get("ticker") or "—")
        pay = str(r.get("paymentDate") or r.get("date") or "—")
        rec = str(r.get("recordDate") or "—")
        amt = r.get("dividend") or r.get("adjDividend") or r.get("amount")
        freq = str(r.get("frequency") or r.get("label") or "")
        yld = r.get("yield") or r.get("dividendYield")
        parts = [f"- **{sym}** pago {pay} (record {rec})"]
        if amt is not None:
            parts.append(f"monto {amt}")
        if yld is not None:
            parts.append(f"yield {yld}")
        if freq:
            parts.append(freq)
        lines.append(" · ".join(parts))
    if len(rows) > max_rows:
        lines.append(f"\n… y {len(rows) - max_rows} filas más (aumenta limit o acota fechas).")
    return "\n".join(lines)


def _row_payment_date(row: dict[str, Any]) -> Optional[date]:
    raw = str(row.get("paymentDate") or row.get("date") or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except Exception:
        return None


class FmpStockDividendsInput(BaseModel):
    symbol: str = Field(..., description="Ticker bursátil (ej. AAPL, MU).")
    limit: int = Field(default=40, ge=1, le=80, description="Máximo de filas recientes a devolver.")


class FmpDividendsCalendarInput(BaseModel):
    from_date: str = Field(..., description="Inicio del rango (YYYY-MM-DD).")
    to_date: str = Field(..., description="Fin del rango (YYYY-MM-DD).")
    limit: int = Field(default=200, ge=1, le=200, description="Máximo de filas del calendario.")


def _get_fmp_stock_dividends_impl(symbol: str, limit: int = 40) -> str:
    sym = (symbol or "").strip().upper()
    if not sym or not sym.replace(".", "").isalnum():
        return "Indica un symbol válido (ej. AAPL)."
    try:
        data = _fmp_get_json("stable/dividends", {"symbol": sym})
    except ValueError as e:
        return str(e)

    if not isinstance(data, list):
        return f"FMP devolvió un formato inesperado para dividendos de {sym}."
    rows = [r for r in data if isinstance(r, dict)]
    rows.sort(key=_dividend_sort_key, reverse=True)
    today = date.today()
    upcoming = [r for r in rows if (_row_payment_date(r) is not None and _row_payment_date(r) >= today)]
    latest_paid = next((r for r in rows if (_row_payment_date(r) is not None and _row_payment_date(r) < today)), None)
    summary_lines = [f"Fecha de referencia (hoy): {today.isoformat()}"]
    if upcoming:
        nxt = sorted(upcoming, key=lambda r: _row_payment_date(r) or today)[0]
        nxt_pay = str(nxt.get("paymentDate") or nxt.get("date") or "—")
        nxt_record = str(nxt.get("recordDate") or "—")
        nxt_amt = nxt.get("dividend") or nxt.get("adjDividend") or nxt.get("amount")
        summary_lines.append(
            f"Próximo pago confirmado (>= hoy): {nxt_pay} (record {nxt_record}, monto {nxt_amt})"
        )
    else:
        summary_lines.append("Próximo pago confirmado (>= hoy): no disponible en los datos devueltos por FMP.")
        if latest_paid is not None:
            lp_pay = str(latest_paid.get("paymentDate") or latest_paid.get("date") or "—")
            lp_amt = latest_paid.get("dividend") or latest_paid.get("adjDividend") or latest_paid.get("amount")
            summary_lines.append(f"Último pago registrado (< hoy): {lp_pay} (monto {lp_amt})")
    details = _format_dividend_rows(rows, title=f"Dividendos FMP — {sym} (últimos hasta {limit})", max_rows=limit)
    return "\n".join(summary_lines + ["", details])


def _get_fmp_dividends_calendar_impl(from_date: str, to_date: str, limit: int = 200) -> str:
    try:
        d0 = _parse_iso_date("from_date", from_date)
        d1 = _parse_iso_date("to_date", to_date)
    except ValueError as e:
        return str(e)
    if d0 > d1:
        return "from_date no puede ser posterior a to_date."
    if (d1 - d0).days > _MAX_CALENDAR_SPAN_DAYS:
        return f"El rango no puede superar {_MAX_CALENDAR_SPAN_DAYS} días (recibido {(d1 - d0).days})."

    f_s = d0.isoformat()
    t_s = d1.isoformat()
    try:
        data = _fmp_get_json("stable/dividends-calendar", {"from": f_s, "to": t_s})
    except ValueError as e:
        return str(e)

    if not isinstance(data, list):
        return "FMP devolvió un formato inesperado para dividends-calendar."
    rows = [r for r in data if isinstance(r, dict)]
    rows.sort(key=_dividend_sort_key)
    title = f"Calendario dividendos FMP {f_s} … {t_s} (hasta {limit} filas)"
    return _format_dividend_rows(rows, title=title, max_rows=limit)


def _stock_dividends_tool(config: Optional[dict] = None) -> Any:
    from langchain_core.tools import StructuredTool

    def _run(symbol: str, limit: int = 40) -> str:
        return _get_fmp_stock_dividends_impl(symbol, limit)

    return StructuredTool.from_function(
        name="get_fmp_stock_dividends",
        description=(
            "Historial/reciente de dividendos de UN ticker vía Financial Modeling Prep (FMP). "
            "Usar para: yield, fechas record/payment, monto por acción. "
            "Requiere FMP_API_KEY. No sustituye get_ibkr_portfolio (cuenta propia)."
        ),
        func=_run,
        args_schema=FmpStockDividendsInput,
    )


def _dividends_calendar_tool(config: Optional[dict] = None) -> Any:
    from langchain_core.tools import StructuredTool

    def _run(from_date: str, to_date: str, limit: int = 200) -> str:
        return _get_fmp_dividends_calendar_impl(from_date, to_date, limit)

    return StructuredTool.from_function(
        name="get_fmp_dividends_calendar",
        description=(
            "Calendario global de dividendos FMP entre dos fechas (YYYY-MM-DD), máximo 90 días de ventana. "
            "Usar para: qué empresas pagan dividendos en una semana/mes. "
            "Requiere FMP_API_KEY."
        ),
        func=_run,
        args_schema=FmpDividendsCalendarInput,
    )


def register_fmp_skill(tools_list: list[Any], fmp_config: Optional[dict] = None) -> None:
    """
    Registra get_fmp_stock_dividends y get_fmp_dividends_calendar.
    fmp_config None → no registrar. enabled: false → no registrar.
    """
    if fmp_config is None:
        return
    cfg = fmp_config if isinstance(fmp_config, dict) else {}
    if cfg.get("enabled") is False:
        return
    try:
        tools_list.append(_stock_dividends_tool(cfg))
        tools_list.append(_dividends_calendar_tool(cfg))
    except Exception:
        _log.debug("register_fmp_skill omitido", exc_info=True)
