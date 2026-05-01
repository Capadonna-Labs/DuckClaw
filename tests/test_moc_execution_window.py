"""Parser compartido de ventana MOC (gateway + quant_trader_bridge)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from duckclaw.forge.skills.moc_execution_window import parse_moc_execution_window_bounds


def test_default_window_ends_at_145930() -> None:
    s, e, lab = parse_moc_execution_window_bounds(environ={})
    assert s == 14 * 3600 + 40 * 60
    assert e == 14 * 3600 + 59 * 60 + 30
    assert lab == "14:40-14:59:30"


def test_legacy_hh_mm_without_seconds() -> None:
    s, e, lab = parse_moc_execution_window_bounds(
        environ={"DUCKCLAW_QUANT_AUTO_EXECUTE_MOC_WINDOW": "14:40-14:55"}
    )
    assert s == 14 * 3600 + 40 * 60
    assert e == 14 * 3600 + 55 * 60
    assert lab == "14:40-14:55"


def test_seconds_on_start_only() -> None:
    s, e, _ = parse_moc_execution_window_bounds(
        environ={"DUCKCLAW_QUANT_AUTO_EXECUTE_MOC_WINDOW": "14:40:05-14:59:30"}
    )
    assert s == 14 * 3600 + 40 * 60 + 5
    assert e == 14 * 3600 + 59 * 60 + 30


def test_inclusive_end_second_via_datetime() -> None:
    dt_in = datetime(2026, 5, 1, 14, 59, 30, tzinfo=ZoneInfo("America/Bogota"))
    cur = dt_in.hour * 3600 + dt_in.minute * 60 + dt_in.second
    start_s, end_s, _ = parse_moc_execution_window_bounds(environ={})
    assert start_s <= cur <= end_s
    dt_out = datetime(2026, 5, 1, 14, 59, 31, tzinfo=ZoneInfo("America/Bogota"))
    cur2 = dt_out.hour * 3600 + dt_out.minute * 60 + dt_out.second
    assert not (start_s <= cur2 <= end_s)
