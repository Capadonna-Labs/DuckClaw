"""
Validación Finanz + contrato HTTP OHLCV (/api/market/ohlcv con clave ``data``).

- ``fetch_market_data`` persiste en ``quant_core.ohlcv_data`` cuando el timeframe va
  por HTTP (p. ej. ``1h`` sin ruta lake) y la respuesta sigue el contrato DuckClaw.
- El manifest Finanz con ``quant.enabled: true`` registra la tool ``fetch_market_data``.
"""

from __future__ import annotations

import json
import sys
import types
from unittest.mock import MagicMock, patch

import duckdb
import pytest

from duckclaw.forge.skills.quant_market_bridge import (
    _fetch_market_data_impl,
    finanz_reconcile_reply_with_fetch_market_tool,
)
from duckclaw.workers.factory import _finanz_user_requests_ohlcv_ingest
from duckclaw.workers.manifest import load_manifest


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


def test_fetch_market_data_http_success_contract_data_array(
    monkeypatch: pytest.MonkeyPatch, quant_db: duckdb.DuckDBPyConnection
) -> None:
    monkeypatch.setenv(
        "IBKR_MARKET_DATA_URL",
        "http://127.0.0.1:8002/api/market/ohlcv",
    )
    monkeypatch.delenv("CAPADONNA_SSH_HOST", raising=False)

    payload = {
        "status": "success",
        "ticker": "USO",
        "timeframe": "1h",
        "data": [
            {
                "timestamp": "2026-04-01T09:30:00Z",
                "open": 81.5,
                "high": 82.1,
                "low": 81.2,
                "close": 81.95,
                "volume": 1_500_000,
            }
        ],
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
    cm = MagicMock()
    cm.__enter__.return_value = mock_resp
    cm.__exit__.return_value = None

    with patch("duckclaw.forge.skills.quant_market_bridge.urllib.request.urlopen", return_value=cm):
        out = _fetch_market_data_impl(
            quant_db, ticker="USO", timeframe="1h", lookback_days=7
        )

    body = json.loads(out)
    assert body.get("status") == "ok"
    assert body.get("source") == "ibkr_http"
    assert body.get("rows_upserted") == 1

    row = quant_db.execute(
        "SELECT ticker, volume FROM quant_core.ohlcv_data WHERE ticker = 'USO'"
    ).fetchone()
    assert row is not None
    assert row[0] == "USO"
    assert row[1] == pytest.approx(1_500_000.0)


def test_fetch_market_data_intraday_http_not_lake_when_capadonna_configured(
    monkeypatch: pytest.MonkeyPatch, quant_db: duckdb.DuckDBPyConnection
) -> None:
    """1h no está en CAPADONNA_HISTORICAL_TIMEFRAMES por defecto → siempre HTTP si URL hay."""
    monkeypatch.setenv(
        "IBKR_MARKET_DATA_URL",
        "http://127.0.0.1:8002/api/market/ohlcv",
    )
    monkeypatch.setenv("CAPADONNA_SSH_HOST", "100.97.151.69")
    monkeypatch.setenv(
        "CAPADONNA_REMOTE_OHLC_CMD",
        "/home/capadonna/.venv/bin/python /home/capadonna/scripts/lake.py {ticker} {timeframe} {lookback_days}",
    )

    payload = {
        "status": "success",
        "ticker": "SPY",
        "timeframe": "1h",
        "data": [
            {
                "timestamp": "2026-04-01T10:00:00Z",
                "open": 500.0,
                "high": 501.0,
                "low": 499.0,
                "close": 500.5,
                "volume": 1_000_000,
            }
        ],
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
    cm = MagicMock()
    cm.__enter__.return_value = mock_resp
    cm.__exit__.return_value = None

    with patch("duckclaw.forge.skills.quant_market_bridge.urllib.request.urlopen", return_value=cm):
        out = _fetch_market_data_impl(
            quant_db, ticker="SPY", timeframe="1h", lookback_days=7
        )

    body = json.loads(out)
    assert body.get("source") == "ibkr_http"
    assert body.get("rows_upserted") == 1


def test_finanz_reconcile_reply_when_model_claims_offline_but_tool_ok() -> None:
    try:
        from langchain_core.messages import AIMessage, ToolMessage
    except ImportError:
        pytest.skip("langchain_core messages not available")

    bad_ai = (
        "## ERROR\n🔴 Ceguera Sensorial: Lake Capadonna fuera de alcance\n"
        "`fetch_market_data` CAPADONNA_OFFLINE Gateway SSH al VPS completamente offline"
    )
    tool_json = json.dumps(
        {
            "status": "ok",
            "ticker": "SPY",
            "rows_upserted": 17,
            "timeframe": "1h",
            "lookback_days": 7,
            "source": "ibkr_http",
        },
        ensure_ascii=False,
    )
    msgs = [
        ToolMessage(
            content=tool_json,
            name="fetch_market_data",
            tool_call_id="call-unit-test-1",
        ),
        AIMessage(content=bad_ai),
    ]
    out = finanz_reconcile_reply_with_fetch_market_tool(msgs, bad_ai)
    assert "correcto" in out.lower()
    assert "SPY" in out
    assert "ibkr_http" in out
    assert "17" in out


def test_finanz_reconcile_skips_when_reply_success_but_mentions_capadonna_footnote() -> None:
    """PM2/trace: modelo acertó ingesta + read_sql pero nota al pie cita CAPADONNA_OFFLINE."""
    try:
        from langchain_core.messages import AIMessage, ToolMessage
    except ImportError:
        pytest.skip("langchain_core messages not available")

    good_ai = (
        "## ✅ INGESTA SPY 1H EXITOSA\n\n"
        "1. **`fetch_market_data`:** ✅ Estado: `ok`, **45** filas.\n"
        "2. **`quant_core.ohlcv_data`:** Total filas para SPY: **45**\n\n"
        "⚠️ El Lake Capadonna sigue offline (`CAPADONNA_OFFLINE`), pero IBKR HTTP funcionó.\n"
    )
    tool_json = json.dumps(
        {
            "status": "ok",
            "ticker": "SPY",
            "rows_upserted": 45,
            "timeframe": "1h",
            "lookback_days": 7,
            "source": "ibkr_http",
        },
        ensure_ascii=False,
    )
    msgs = [
        ToolMessage(
            content=tool_json,
            name="fetch_market_data",
            tool_call_id="call-unit-test-2",
        ),
        AIMessage(content=good_ai),
    ]
    out = finanz_reconcile_reply_with_fetch_market_tool(msgs, good_ai)
    assert out == good_ai
    assert "## Ingesta OHLCV" not in out


def test_finanz_manifest_registers_quant_for_market_tools() -> None:
    spec = load_manifest("finanz")
    assert isinstance(spec.quant_config, dict)
    assert spec.quant_config.get("enabled") is True
    assert (spec.logical_worker_id or spec.worker_id or "").lower() == "finanz"

    db = _memory_quant_db()
    tools: list = []
    from duckclaw.forge.skills.quant_market_bridge import register_quant_market_skill

    register_quant_market_skill(db, tools, spec)
    names = {getattr(t, "name", None) for t in tools}
    assert "fetch_market_data" in names
    assert "fetch_lake_ohlcv" in names


def test_finanz_ohlcv_ingest_intent_velas_and_ticker() -> None:
    assert _finanz_user_requests_ohlcv_ingest(
        "Trae velas de SPY en 1h, últimos 7 días y confirma filas en quant_core.ohlcv_data"
    )


def test_finanz_ohlcv_ingest_intent_rejects_plain_candles_chat() -> None:
    assert not _finanz_user_requests_ohlcv_ingest("Explícame qué son las velas japonesas en bolsa")


def test_finanz_ohlcv_ingest_intent_quant_core_explicit() -> None:
    assert _finanz_user_requests_ohlcv_ingest(
        "Descarga OHLCV y actualiza quant_core.ohlcv_data para GLD"
    )


def test_finanz_ohlcv_ingest_rejects_meta_vlm_gateway_down() -> None:
    """META VLM: «ingesta» + MLX/VLM en mayúsculas no deben disparar OHLCV."""
    meta = (
        "[META: VLM_GATEWAY_DOWN] El usuario envió una imagen por Telegram (sin caption); "
        "el servicio de visión no produjo resumen (p. ej. MLX en DUCKCLAW_VLM_MLX_BASE_URL). "
        "No hay bloque [VLM_CONTEXT]. Aquí falló la ingesta VLM, no el rol del asistente."
    )
    assert not _finanz_user_requests_ohlcv_ingest(meta)


def test_finanz_ohlcv_ingest_quant_core_still_accepts_ingesta_verb() -> None:
    assert _finanz_user_requests_ohlcv_ingest(
        "Ingesta quant_core.ohlcv_data para AAPL con datos frescos"
    )


def test_fetch_market_data_vix_uses_yfinance(
    monkeypatch: pytest.MonkeyPatch, quant_db: duckdb.DuckDBPyConnection
) -> None:
    """VIX prioriza yfinance (^VIX) aunque lake/HTTP estén configurados."""
    pd = pytest.importorskip("pandas")

    monkeypatch.setenv("CAPADONNA_SSH_HOST", "100.97.151.69")
    monkeypatch.setenv(
        "CAPADONNA_REMOTE_OHLC_CMD",
        "echo {}",
    )
    monkeypatch.setenv(
        "IBKR_MARKET_DATA_URL",
        "http://127.0.0.1:8002/api/market/ohlcv",
    )

    df = pd.DataFrame(
        {
            "Open": [20.0],
            "High": [21.0],
            "Low": [19.0],
            "Close": [20.5],
            "Volume": [1.0],
        },
        index=pd.DatetimeIndex([pd.Timestamp("2026-04-01 16:00:00", tz="UTC")]),
    )

    class _FakeTicker:
        def history(self, **kwargs):
            return df

    fake_yf = types.ModuleType("yfinance")

    def _ticker(_sym: str):
        return _FakeTicker()

    fake_yf.Ticker = _ticker
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)
    out = _fetch_market_data_impl(
        quant_db, ticker="^VIX", timeframe="1d", lookback_days=30
    )

    body = json.loads(out)
    assert body.get("status") == "ok"
    assert body.get("source") == "yfinance"
    assert body.get("ticker") == "VIX"
    row = quant_db.execute(
        "SELECT ticker, close FROM quant_core.ohlcv_data WHERE ticker = 'VIX'"
    ).fetchone()
    assert row is not None
    assert row[0] == "VIX"
    assert row[1] == pytest.approx(20.5)
