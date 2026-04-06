#!/usr/bin/env python3
"""
Imprime JSON {\"bars\":[...]} en stdout para IB Gateway (ib_async), mismo contrato
que export_lake_ohlcv (timestamp, open, high, low, close, volume).

Uso (en el VPS junto a TWS/Gateway):
  python ibkr_historical_bars.py TICKER TIMEFRAME LOOKBACK_DAYS

Entorno típico:
  IB_HOST=127.0.0.1  IB_PORT=4002|4001  IB_CLIENT_ID=17  IB_ENV=paper|live

Requisito: Python 3.10+, pip install ib_async en el venv del proyecto Capadonna-Driller.
ETFs/acciones US: contrato Stock(ticker, 'SMART', 'USD'). Ajustar si el símbolo exige otro exchange.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any


def _emit(bars: list[dict[str, Any]], *, note: str | None = None) -> None:
    payload: dict[str, Any] = {"bars": bars}
    if note:
        payload["message"] = note
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def _bar_setting_and_cap(tf: str) -> tuple[str, int]:
    """(barSizeSetting, max_duration_days recomendado para esa granularidad)."""
    t = (tf or "1d").strip()
    tl = t.lower()
    if t == "1M":
        return "1 month", 365 * 5
    if tl in ("1m",):
        return "1 min", 30
    if tl in ("2m",):
        return "2 mins", 60
    if tl in ("3m",):
        return "3 mins", 90
    if tl in ("5m",):
        return "5 mins", 180
    if tl in ("10m",):
        return "10 mins", 180
    if tl in ("15m",):
        return "15 mins", 365
    if tl in ("30m",):
        return "30 mins", 365
    if tl in ("1h", "60m"):
        return "1 hour", 365
    if tl in ("2h",):
        return "2 hours", 365 * 2
    if tl in ("4h",):
        return "4 hours", 365 * 3
    if tl in ("1d", "daily"):
        return "1 day", 365 * 5
    if tl in ("1w",):
        return "1 week", 365 * 10
    return "1 day", 365


def _duration_str(lookback_days: int, cap_days: int) -> str:
    d = max(1, min(int(lookback_days), cap_days, 365 * 20))
    if d <= 364:
        return f"{d} D"
    y = max(1, d // 365)
    return f"{y} Y"


async def main_async() -> None:
    try:
        from ib_async import IB, Stock
    except ImportError:
        _emit([], note="ib_async not installed; pip install ib_async in project venv")

    if len(sys.argv) < 4:
        _emit([], note="Uso: ibkr_historical_bars.py TICKER TIMEFRAME LOOKBACK_DAYS")

    ticker = sys.argv[1].strip().upper()
    timeframe = sys.argv[2].strip()
    try:
        lookback_days = max(1, min(int(sys.argv[3]), 4000))
    except ValueError:
        lookback_days = 30

    host = (os.environ.get("IB_HOST") or "127.0.0.1").strip()
    try:
        port = int((os.environ.get("IB_PORT") or "").strip() or "0")
    except ValueError:
        port = 0
    if port <= 0:
        ib_env = (os.environ.get("IB_ENV") or os.environ.get("TWS_ENV") or "paper").lower()
        port = 4002 if ib_env == "paper" else 4001
    try:
        client_id = int((os.environ.get("IB_CLIENT_ID") or "42").strip())
    except ValueError:
        client_id = 42

    bar_size, cap = _bar_setting_and_cap(timeframe)
    duration = _duration_str(lookback_days, cap)

    ib = IB()
    try:
        await ib.connectAsync(host, port, clientId=client_id, timeout=30)
    except Exception as e:
        print(
            json.dumps(
                {"bars": [], "message": f"IB connect failed: {e!s}"},
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    bars: list[Any] = []
    try:
        contract = Stock(ticker, "SMART", "USD")
        await ib.qualifyContractsAsync(contract)
        bars = await ib.reqHistoricalDataAsync(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
    except Exception as e:
        ib.disconnect()
        print(
            json.dumps(
                {"bars": [], "message": f"IB historical error: {e!s}"},
                ensure_ascii=False,
            )
        )
        sys.exit(1)
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass

    out: list[dict[str, Any]] = []
    for b in bars:
        dt = b.date
        if hasattr(dt, "tzinfo") and dt.tzinfo is None and hasattr(dt, "replace"):
            dt = dt.replace(tzinfo=timezone.utc)
        if isinstance(dt, datetime):
            ts = dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            ts = str(dt)
        out.append(
            {
                "ticker": ticker,
                "timestamp": ts,
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(getattr(b, "volume", 0) or 0),
            }
        )

    _emit(out, note=f"source=ib_gateway barSize={bar_size} duration={duration}" if out else "IB returned zero bars")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
