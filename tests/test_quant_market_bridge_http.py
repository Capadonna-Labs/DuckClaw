"""Tests for IBKR OHLCV HTTP client (_http_fetch_json) in quant_market_bridge."""

from __future__ import annotations

import io
import json
import os
import urllib.error
from unittest.mock import patch

import pytest

from duckclaw.forge.skills.quant_market_bridge import _http_fetch_json


@pytest.fixture
def market_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IBKR_MARKET_DATA_URL", "http://127.0.0.1:8002/api/market/ohlcv")
    monkeypatch.delenv("IBKR_PORTFOLIO_API_KEY", raising=False)
    monkeypatch.delenv("IBKR_MARKET_DATA_API_KEY", raising=False)


def test_http_error_body_message_surfaced(market_url: None) -> None:
    body = json.dumps(
        {"status": "error", "message": "Market data farm connection is OK but missing subscription for USO"}
    )
    fp = io.BytesIO(body.encode("utf-8"))
    err = urllib.error.HTTPError("http://127.0.0.1:8002/api/market/ohlcv", 400, "Bad Request", {}, fp)

    with patch("urllib.request.urlopen", side_effect=err):
        _payload, err_s = _http_fetch_json("USO", "1h", 7)

    assert _payload is None
    assert err_s is not None
    parsed = json.loads(err_s)
    assert "missing subscription for USO" in parsed["error"]
    assert parsed["error"].startswith("HTTP 400:")


def test_http_error_fallback_when_body_not_json(market_url: None) -> None:
    fp = io.BytesIO(b"not json")
    err = urllib.error.HTTPError("http://127.0.0.1:8002/api/market/ohlcv", 500, "Error", {}, fp)

    with patch("urllib.request.urlopen", side_effect=err):
        _payload, err_s = _http_fetch_json("AAPL", "1d", 30)

    assert _payload is None
    parsed = json.loads(err_s)
    assert "mercado no disponible" in parsed["error"]
