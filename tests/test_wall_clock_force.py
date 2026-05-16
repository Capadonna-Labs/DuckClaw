"""Tests for wall-clock refresh helpers (Quant-Trader get_current_time force)."""

from __future__ import annotations

from duckclaw.workers.factory import _response_mentions_wall_clock


def test_response_mentions_wall_clock_quant_header() -> None:
    assert _response_mentions_wall_clock("Quant-Trader 23 · Sábado 08:46 COT — mercado cerrado")


def test_response_mentions_wall_clock_negative() -> None:
    assert not _response_mentions_wall_clock("Sin impacto en cartera según el post de Reddit.")
