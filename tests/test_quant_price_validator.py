"""Tests for quant_reply_price_audit (Finanz OHLC vs reply text)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from duckclaw.forge.atoms.quant_price_validator import quant_reply_price_audit


class _FakeSpec:
    logical_worker_id = "finanz"
    worker_id = "finanz"
    quant_config = {"enabled": True}


@pytest.fixture
def db_spy_two_closes() -> MagicMock:
    db = MagicMock()

    def query(sql: str) -> str:
        s = (sql or "").upper()
        if "DISTINCT" in s:
            return json.dumps([{"t": "SPY"}])
        if "ORDER BY TIMESTAMP DESC" in s:
            return json.dumps([{"close": "657.25"}])
        return "[]"

    db.query.side_effect = query
    return db


def test_quant_audit_allows_intrabar_close_from_read_sql_evidence(
    db_spy_two_closes: MagicMock,
) -> None:
    try:
        from langchain_core.messages import ToolMessage
    except ImportError:
        pytest.skip("langchain_core not available")

    from duckclaw.forge.atoms.quant_price_validator import _ohlc_numbers_from_messages_for_ticker

    tool_rows = [
        {"ticker": "SPY", "timestamp": "2026-04-06 11:00:00", "close": "657.25"},
        {"ticker": "SPY", "timestamp": "2026-04-06 09:30:00", "close": "658.53"},
    ]
    msgs = [
        ToolMessage(
            content=json.dumps(tool_rows, ensure_ascii=False),
            name="read_sql",
            tool_call_id="t1",
        ),
    ]
    assert 658.53 in _ohlc_numbers_from_messages_for_ticker(msgs, "SPY")

    reply = (
        "## SPY\n"
        "- Último cierre: $657.25 (11:00)\n"
        "- Vela 09:30 close $658.53\n"
    )
    out, reason = quant_reply_price_audit(db_spy_two_closes, _FakeSpec(), reply, messages=msgs)
    assert reason is None
    assert "657.25" in out
    assert "658.53" in out


def test_quant_audit_ignores_ibkr_cash_when_spy_is_only_known_ticker(
    db_spy_two_closes: MagicMock,
) -> None:
    """Runtime: IBKR efectivo ($995.54) must not be audited as SPY quote (PM2 finanz log)."""
    reply = (
        "## SPY ingesta\n"
        "- Último cierre: $656.91\n"
        "## Estado actual de cuentas\n"
        "- IBKR: $995.54 USD efectivo\n"
    )
    out, reason = quant_reply_price_audit(db_spy_two_closes, _FakeSpec(), reply, messages=[])
    assert reason is None
    assert "656.91" in out
    assert "995.54" in out


def test_quant_audit_skips_cfd_metric_decimals_like_density(
    db_spy_two_closes: MagicMock,
) -> None:
    """PM2: densidad proxy 0.000152 en análisis CFD no es cotización SPY."""
    reply = (
        "## ANÁLISIS CFD SPY\n"
        "- Densidad (proxy volumen/precio): 0.000152\n"
        "- Temperatura (volatilidad): 0.0027\n"
        "- SPY último close de referencia $657.25\n"
    )
    out, reason = quant_reply_price_audit(db_spy_two_closes, _FakeSpec(), reply, messages=[])
    assert reason is None
    assert "0.000152" in out
    assert "657.25" in out


def test_quant_audit_allows_max_close_from_sql_aggregate_when_last_bar_differs(
    db_spy_two_closes: MagicMock,
) -> None:
    """PM2: modelo cita max_close 658.53 de read_sql aunque último close en DB sea 656.64."""
    try:
        from langchain_core.messages import ToolMessage
    except ImportError:
        pytest.skip("langchain_core not available")

    def query(sql: str) -> str:
        s = (sql or "").upper()
        if "DISTINCT" in s:
            return json.dumps([{"t": "SPY"}])
        if "ORDER BY TIMESTAMP DESC" in s:
            return json.dumps([{"close": "656.64"}])
        return "[]"

    db_spy_two_closes.query.side_effect = query
    agg = [
        {
            "total_filas": "45",
            "max_close": "658.53",
            "min_close": "631.75",
        },
    ]
    msgs = [
        ToolMessage(
            content=json.dumps(agg, ensure_ascii=False),
            name="read_sql",
            tool_call_id="t1",
        ),
    ]
    reply = "SPY: último cierre reportado $658.53 (máximo ventana) vs barra más reciente en DB menor."
    out, reason = quant_reply_price_audit(db_spy_two_closes, _FakeSpec(), reply, messages=msgs)
    assert reason is None
    assert "658.53" in out


def test_quant_audit_ohlc_rows_without_ticker_column_from_read_sql(
    db_spy_two_closes: MagicMock,
) -> None:
    """read_sql frecuente: SELECT ... WHERE ticker='SPY' sin proyectar ticker en filas."""
    try:
        from langchain_core.messages import ToolMessage
    except ImportError:
        pytest.skip("langchain_core not available")

    rows = [
        {"timestamp": "2026-04-06 09:30:00", "open": "652.05", "high": "654.63", "low": "650.73", "close": "658.53"},
    ]
    msgs = [
        ToolMessage(
            content=json.dumps(rows, ensure_ascii=False),
            name="read_sql",
            tool_call_id="t1",
        ),
    ]
    reply = "Velas SPY: cierre de muestra $658.53"
    out, reason = quant_reply_price_audit(db_spy_two_closes, _FakeSpec(), reply, messages=msgs)
    assert reason is None


def test_quant_audit_skips_vix_level_when_spy_only_known_ticker(
    db_spy_two_closes: MagicMock,
) -> None:
    """PM2: VIX 24.50 no se audita como cotización SPY."""
    reply = (
        "## Contexto\n"
        "- VIX: 24.50 (volatilidad)\n"
        "- SPY último close $657.25 en quant_core\n"
    )
    out, reason = quant_reply_price_audit(db_spy_two_closes, _FakeSpec(), reply, messages=[])
    assert reason is None
    assert "24.50" in out
    assert "657.25" in out


def test_quant_audit_still_flags_price_not_in_db_or_tools(
    db_spy_two_closes: MagicMock,
) -> None:
    try:
        from langchain_core.messages import ToolMessage
    except ImportError:
        pytest.skip("langchain_core not available")

    msgs = [
        ToolMessage(
            content=json.dumps([{"ticker": "SPY", "close": "657.25"}], ensure_ascii=False),
            name="read_sql",
            tool_call_id="t1",
        ),
    ]
    reply = "SPY cotiza $999.99 según fuentes."
    out, reason = quant_reply_price_audit(db_spy_two_closes, _FakeSpec(), reply, messages=msgs)
    assert reason is not None
    assert "ajustada" in out.lower()
