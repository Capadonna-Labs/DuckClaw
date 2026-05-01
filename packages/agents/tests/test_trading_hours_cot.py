"""Ventanas COT para eventos Quant — specs Core-Satellite."""

from __future__ import annotations

from datetime import datetime

from duckclaw.graphs.trading_hours_cot import (
    COT_TZ_NAME,
    classify_cot_trading_windows,
    format_contex_horario_line,
)
from zoneinfo import ZoneInfo


def _dt(d: str, hh: int, mm: int) -> datetime:
    """d=YYYY-MM-DD, hora Bogotá."""
    return datetime.fromisoformat(d).replace(hour=hh, minute=mm, tzinfo=ZoneInfo(COT_TZ_NAME))


def test_monday_0829_not_in_equity_ref() -> None:
    c = classify_cot_trading_windows(_dt("2026-05-04", 8, 29))
    assert c["weekday_mon_fri"] is True
    assert c["in_equity_ref_window"] is False


def test_monday_0830_in_equity_not_moc() -> None:
    c = classify_cot_trading_windows(_dt("2026-05-04", 8, 30))
    assert c["in_equity_ref_window"] is True
    assert c["in_moc_typical_window"] is False


def test_monday_1500_in_equity_boundary() -> None:
    c = classify_cot_trading_windows(_dt("2026-05-04", 15, 0))
    assert c["in_equity_ref_window"] is True


def test_monday_1501_outside_equity() -> None:
    c = classify_cot_trading_windows(_dt("2026-05-04", 15, 1))
    assert c["in_equity_ref_window"] is False


def test_monday_1445_moc_and_equity() -> None:
    c = classify_cot_trading_windows(_dt("2026-05-04", 14, 45))
    assert c["in_equity_ref_window"] is True
    assert c["in_moc_typical_window"] is True


def test_saturday_1030_no_windows() -> None:
    c = classify_cot_trading_windows(_dt("2026-05-02", 10, 30))
    assert c["weekday_mon_fri"] is False
    assert c["in_equity_ref_window"] is False
    assert c["in_moc_typical_window"] is False


def test_format_contains_contex_tag() -> None:
    line = format_contex_horario_line(_dt("2026-05-04", 14, 45))
    assert line.startswith("[CONTEXTO_HORARIO]")
    assert "America/Bogota" in line


def test_naive_dt_treated_as_cot() -> None:
    naive = datetime(2026, 5, 4, 14, 45, 0)
    c = classify_cot_trading_windows(naive)
    assert c["in_moc_typical_window"] is True
