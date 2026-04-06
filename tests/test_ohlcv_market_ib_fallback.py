"""OHLCV HTTP router: lake vacío + fallback IB (ohlcv_market_routes)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parents[1]
_SVC = _ROOT / "services" / "ibkr-ohlcv-api"
if str(_SVC) not in sys.path:
    sys.path.insert(0, str(_SVC))

import ohlcv_market_routes as om


@pytest.fixture
def ohlcv_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("OHLCV_API_KEY", raising=False)
    monkeypatch.delenv("IBKR_PORTFOLIO_API_KEY", raising=False)
    app = FastAPI()
    app.include_router(om.router)
    return TestClient(app)


def test_market_ohlcv_uses_ib_when_lake_empty(
    ohlcv_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        om,
        "_run_lake_export",
        lambda *a, **k: {"bars": [], "message": "no rows in lake"},
    )
    monkeypatch.setattr(
        om,
        "_run_ib_export",
        lambda *a, **k: {
            "bars": [
                {
                    "timestamp": "2026-01-01 10:00:00",
                    "open": 1.0,
                    "high": 2.0,
                    "low": 0.5,
                    "close": 1.5,
                    "volume": 100.0,
                }
            ],
            "message": "source=ib_gateway",
        },
    )
    monkeypatch.setattr(
        om,
        "_resolve_ib_paths",
        lambda: (
            str(_ROOT / ".venv" / "bin" / "python"),
            str(_ROOT / "scripts" / "capadonna" / "ibkr_historical_bars.py"),
        ),
    )

    r = ohlcv_client.get(
        "/api/market/ohlcv",
        params={"ticker": "USO", "timeframe": "1h", "lookback_days": 7},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "success"
    assert body.get("ticker") == "USO"
    assert len(body.get("data") or []) == 1
    assert body["data"][0]["close"] == 1.5


def test_market_ohlcv_lake_error_ib_disabled_returns_lake_err(
    ohlcv_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.responses import JSONResponse

    lake_resp = JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Lake export exited 1"},
    )
    monkeypatch.setattr(om, "_run_lake_export", lambda *a, **k: lake_resp)
    monkeypatch.setattr(om, "_resolve_ib_paths", lambda: None)

    r = ohlcv_client.get(
        "/api/market/ohlcv",
        params={"ticker": "SPY", "timeframe": "1d", "lookback_days": 30},
    )
    assert r.status_code == 500
    assert "Lake" in r.json().get("message", "") or "Lake" in str(r.json())
