"""Regression: _live_mark_price must fall back to delayed data (type 3) when
realtime (type 1) comes back empty — some IBKR accounts only have realtime
entitlements for a subset of symbols, which is why PRE_FLIGHT_MARK_UNAVAILABLE
hit MU/MSFT/XLU while CEG/SPY worked fine on the same Gateway."""

from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock

# ib_insync isn't installed in this dev venv (only on the VPS where IBKR
# integration actually runs) — _live_mark_price does `from ib_insync import
# Stock` as a local import, so a minimal stand-in module is enough to test
# the mark-price fallback logic without the real dependency.
if "ib_insync" not in sys.modules:
    _fake_ib_insync = types.ModuleType("ib_insync")
    _fake_ib_insync.Stock = lambda *args, **kwargs: MagicMock()
    sys.modules["ib_insync"] = _fake_ib_insync

from duckclaw.signal_execution_bridge import _live_mark_price, _open_orders_for_ticker


def _make_ib(ticker_sequence):
    """ticker_sequence: list of dicts, one per reqMktData call, attr->value."""
    ib = MagicMock()
    ib.qualifyContractsAsync = AsyncMock()
    calls = {"data_types": [], "req_count": 0}

    def _req_market_data_type(dt):
        calls["data_types"].append(dt)

    def _req_mkt_data(contract, *_args, **_kwargs):
        idx = calls["req_count"]
        calls["req_count"] += 1
        fields = ticker_sequence[idx] if idx < len(ticker_sequence) else {}
        t = MagicMock()
        for attr in ("marketPrice", "last", "close", "bid", "ask"):
            setattr(t, attr, fields.get(attr))
        return t

    ib.reqMarketDataType.side_effect = _req_market_data_type
    ib.reqMktData.side_effect = _req_mkt_data
    return ib, calls


def test_returns_live_price_without_falling_back() -> None:
    ib, calls = _make_ib([{"marketPrice": 452.3}])
    price = asyncio.run(_live_mark_price(ib, "CEG"))
    assert price == 452.3
    # never had to try delayed (3) — the trailing 1 is the always-run restore
    assert calls["data_types"] == [1, 1]
    assert calls["req_count"] == 1


def test_falls_back_to_delayed_when_live_is_empty() -> None:
    ib, calls = _make_ib(
        [
            {},  # live attempt: nothing populated
            {"last": 980.5},  # delayed attempt: has a last price
        ]
    )
    price = asyncio.run(_live_mark_price(ib, "MU"))
    assert price == 980.5
    assert calls["data_types"] == [1, 3, 1]  # trailing 1 = restore
    assert calls["req_count"] == 2


def test_restores_live_data_type_when_both_attempts_empty() -> None:
    ib, calls = _make_ib([{}, {}])
    price = asyncio.run(_live_mark_price(ib, "XLU"))
    assert price is None
    # tries 1, then 3, then restores to 1 in the finally block
    assert calls["data_types"] == [1, 3, 1]


def test_open_orders_for_ticker_uses_async_variant() -> None:
    """Regression: reqAllOpenOrders() (sync) blocks via loop.run_until_complete()
    and raises "This event loop is already running" when called from inside a
    coroutine that's already running on an event loop (exactly the preflight
    call path) — reqAllOpenOrdersAsync() is the correct equivalent here."""
    ib = MagicMock()
    ib.reqAllOpenOrdersAsync = AsyncMock()
    trade = MagicMock()
    trade.contract.symbol = "MU"
    ib.openTrades.return_value = [trade]

    result = asyncio.run(_open_orders_for_ticker(ib, "MU"))

    ib.reqAllOpenOrdersAsync.assert_awaited_once()
    ib.reqAllOpenOrders.assert_not_called()
    assert result == [trade]
