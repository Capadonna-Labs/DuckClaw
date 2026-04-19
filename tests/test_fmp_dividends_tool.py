"""Tests FMP dividend tools (mocked HTTP)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from duckclaw.forge.skills import fmp_bridge as fb
from duckclaw.forge.skills.fmp_bridge import register_fmp_skill


@pytest.fixture
def fmp_key(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test-key")


def _mock_urlopen_response(payload: object, status: int = 200):
    raw = json.dumps(payload).encode("utf-8")
    cm = MagicMock()
    cm.read.return_value = raw
    cm.__enter__.return_value = cm
    cm.status = status
    return cm


def test_stock_dividends_no_key(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    out = fb._get_fmp_stock_dividends_impl("AAPL", 5)
    assert "FMP_API_KEY" in out


def test_stock_dividends_ok(fmp_key):
    payload = [
        {
            "symbol": "AAPL",
            "date": "2024-02-10",
            "paymentDate": "2024-02-15",
            "recordDate": "2024-02-12",
            "dividend": 0.24,
        }
    ]
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_response(payload)):
        out = fb._get_fmp_stock_dividends_impl("aapl", 5)
    assert "AAPL" in out
    assert "0.24" in out or "pago" in out.lower()


def test_stock_dividends_marks_no_future_payment(fmp_key, monkeypatch):
    class _FakeDate:
        @classmethod
        def today(cls):
            return fb.datetime.strptime("2026-04-17", "%Y-%m-%d").date()

    monkeypatch.setattr(fb, "date", _FakeDate)
    payload = [
        {"symbol": "GOOGL", "paymentDate": "2026-03-16", "recordDate": "2026-03-09", "dividend": 0.21},
        {"symbol": "GOOGL", "paymentDate": "2025-12-15", "recordDate": "2025-12-08", "dividend": 0.21},
    ]
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_response(payload)):
        out = fb._get_fmp_stock_dividends_impl("googl", 10)
    assert "Fecha de referencia (hoy): 2026-04-17" in out
    assert "Próximo pago confirmado (>= hoy): no disponible" in out
    assert "Último pago registrado (< hoy): 2026-03-16" in out


def test_stock_dividends_marks_upcoming_payment(fmp_key, monkeypatch):
    class _FakeDate:
        @classmethod
        def today(cls):
            return fb.datetime.strptime("2026-04-17", "%Y-%m-%d").date()

    monkeypatch.setattr(fb, "date", _FakeDate)
    payload = [
        {"symbol": "AAPL", "paymentDate": "2026-05-15", "recordDate": "2026-05-12", "dividend": 0.25},
        {"symbol": "AAPL", "paymentDate": "2026-02-13", "recordDate": "2026-02-10", "dividend": 0.25},
    ]
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_response(payload)):
        out = fb._get_fmp_stock_dividends_impl("aapl", 10)
    assert "Próximo pago confirmado (>= hoy): 2026-05-15" in out


def test_calendar_range_too_long(fmp_key):
    out = fb._get_fmp_dividends_calendar_impl("2024-01-01", "2024-06-01", 50)
    assert "90" in out


def test_calendar_invalid_date(fmp_key):
    out = fb._get_fmp_dividends_calendar_impl("not-a-date", "2024-01-10", 50)
    assert "YYYY-MM-DD" in out


def test_calendar_from_after_to(fmp_key):
    out = fb._get_fmp_dividends_calendar_impl("2024-02-10", "2024-01-01", 50)
    assert "no puede" in out.lower()


def test_calendar_ok(fmp_key):
    payload = [
        {"symbol": "MSFT", "paymentDate": "2024-02-14", "recordDate": "2024-02-08", "dividend": 0.75},
    ]
    with patch("urllib.request.urlopen", return_value=_mock_urlopen_response(payload)):
        out = fb._get_fmp_dividends_calendar_impl("2024-02-01", "2024-02-20", 10)
    assert "MSFT" in out


def test_register_fmp_skill_none():
    tools: list = []
    register_fmp_skill(tools, None)
    assert tools == []


def test_register_fmp_skill_enabled_adds_two():
    tools: list = []
    register_fmp_skill(tools, {})
    assert len(tools) == 2
    names = {t.name for t in tools}
    assert names == {"get_fmp_stock_dividends", "get_fmp_dividends_calendar"}


def test_register_fmp_skill_disabled():
    tools: list = []
    register_fmp_skill(tools, {"enabled": False})
    assert tools == []
