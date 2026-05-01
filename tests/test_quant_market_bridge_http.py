"""Tests for IBKR OHLCV HTTP client (_http_fetch_json) in quant_market_bridge."""

from __future__ import annotations

import io
import json
import os
import urllib.error
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from duckclaw.forge.skills import quant_market_bridge as qmb
from duckclaw.forge.skills.quant_market_bridge import (
    _fetch_ib_gateway_ohlcv_impl,
    _http_fetch_json,
)


def _memory_quant_db() -> duckdb.DuckDBPyConnection:
    db = duckdb.connect(":memory:")
    db.execute("CREATE SCHEMA quant_core;")
    db.execute(
        """
        CREATE TABLE quant_core.ohlcv_data (
            ticker VARCHAR,
            timestamp TIMESTAMP,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume DOUBLE,
            PRIMARY KEY (ticker, timestamp)
        );
        """
    )
    return db


@pytest.fixture
def quant_db() -> duckdb.DuckDBPyConnection:
    return _memory_quant_db()


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


def test_fetch_ib_gateway_ohlcv_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IBKR_GATEWAY_OHLCV_URL", raising=False)
    monkeypatch.delenv("IBKR_MARKET_DATA_URL", raising=False)
    monkeypatch.delenv("CAPADONNA_SSH_HOST", raising=False)
    monkeypatch.delenv("CAPADONNA_REMOTE_OHLC_CMD", raising=False)

    class _Db:
        pass

    raw = _fetch_ib_gateway_ohlcv_impl(_Db(), ticker="SPY", timeframe="1h", lookback_days=7)
    body = json.loads(raw)
    assert body.get("error") == "IBKR_GATEWAY_OHLCV_UNCONFIGURED"


def test_fetch_ib_gateway_ohlcv_delegates_to_lake_when_configured(
    monkeypatch: pytest.MonkeyPatch, quant_db: duckdb.DuckDBPyConnection
) -> None:
    monkeypatch.delenv("IBKR_GATEWAY_OHLCV_URL", raising=False)
    monkeypatch.delenv("IBKR_MARKET_DATA_URL", raising=False)
    monkeypatch.setenv("CAPADONNA_SSH_HOST", "100.97.151.69")
    monkeypatch.setenv(
        "CAPADONNA_REMOTE_OHLC_CMD",
        "/venv/bin/python /scripts/export_lake_ohlcv.py {ticker} {timeframe} {lookback_days}",
    )
    monkeypatch.setenv("CAPADONNA_HISTORICAL_TIMEFRAMES", "1d,1w,1M,moc")
    monkeypatch.setenv("IBKR_REALTIME_TIMEFRAMES", "1m,5m,15m,30m,1h")

    lake_payload = {
        "bars": [
            {
                "timestamp": "2026-04-01T00:00:00Z",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1_000_000.0,
            }
        ]
    }

    with patch.object(qmb, "_run_lake_ssh_json", return_value=(lake_payload, None)):
        raw = _fetch_ib_gateway_ohlcv_impl(quant_db, ticker="SPY", timeframe="1d", lookback_days=30)

    body = json.loads(raw)
    assert body.get("status") == "ok"
    assert body.get("source") == "lake_ssh"
    row = quant_db.execute(
        "SELECT ticker FROM quant_core.ohlcv_data WHERE ticker = 'SPY'"
    ).fetchone()
    assert row is not None


def test_fetch_ib_gateway_prefers_ibkr_market_http_over_gateway(
    monkeypatch: pytest.MonkeyPatch, quant_db: duckdb.DuckDBPyConnection
) -> None:
    monkeypatch.delenv("CAPADONNA_SSH_HOST", raising=False)
    monkeypatch.setenv(
        "IBKR_MARKET_DATA_URL",
        "http://127.0.0.1:8002/api/market/ohlcv",
    )
    monkeypatch.setenv(
        "IBKR_GATEWAY_OHLCV_URL",
        "http://127.0.0.1:8002/api/market/ibkr/historical",
    )

    payload = {
        "status": "success",
        "ticker": "SPY",
        "timeframe": "1h",
        "data": [
            {
                "timestamp": "2026-04-01T09:30:00Z",
                "open": 500.0,
                "high": 501.0,
                "low": 499.0,
                "close": 500.5,
                "volume": 2_000_000.0,
            }
        ],
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
    cm = MagicMock()
    cm.__enter__.return_value = mock_resp
    cm.__exit__.return_value = None

    with patch("duckclaw.forge.skills.quant_market_bridge.urllib.request.urlopen", return_value=cm) as uo:
        raw = _fetch_ib_gateway_ohlcv_impl(quant_db, ticker="SPY", timeframe="1h", lookback_days=10)

    assert uo.call_count == 1
    first_req = uo.call_args[0][0]
    url = getattr(first_req, "full_url", None) or first_req.get_full_url()
    assert "market/ohlcv" in url
    assert "ibkr/historical" not in url
    body = json.loads(raw)
    assert body.get("status") == "ok"
    assert body.get("source") == "ibkr_http"
