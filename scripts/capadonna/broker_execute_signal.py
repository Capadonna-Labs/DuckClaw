#!/usr/bin/env python3
"""
Hook para ``POST /api/broker/execute`` (Duckclaw ``IBKR_EXECUTE_ORDER_URL``).

Uso (invocado por ``ohlcv_market_routes``):
  python broker_execute_signal.py <signal_id_uuid> <paper>
  ``paper``: ``1`` = cuenta paper, ``0`` = live (puerto IB según env).

Prioridad:
 1) Variable de entorno ``DUCKCLAW_EMBEDDED_EXECUTE_JSON`` (inyectada por el API desde el POST
     enriquecido por el gateway): modo ``weight`` (Quant Trader) o ``shares`` (Finanz).
  2) Fallback: leer ``finance_worker.trade_signals`` en ``IBKR_EXECUTE_ORDER_DB_PATH`` (copia local).

Requisitos: Python 3.10+, ``pip install ib_async``; ``duckdb`` solo si usas fallback DB.

Variables: ver spec Capadonna Lake + broker execute.
``IBKR_MARKET_DATA_TYPE`` (default ``3`` = delayed): evita Error 10089 si no hay suscripción real-time para API.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

RowLoad = tuple[str, str, float] | Literal["missing_db", "not_found"]


@dataclass(frozen=True)
class _WeightPlan:
    ticker: str
    signal_type: str
    weight_pct: float


@dataclass(frozen=True)
class _SharesPlan:
    ticker: str
    action: str
    quantity: float


def _emit(obj: dict[str, Any], *, rc: int) -> None:
    print(json.dumps(obj, ensure_ascii=False))
    sys.exit(rc)


def _db_path() -> str:
    return (
        os.environ.get("IBKR_EXECUTE_ORDER_DB_PATH")
        or os.environ.get("DUCKCLAW_EXECUTE_ORDER_DB_PATH")
        or ""
    ).strip()


def _load_signal_row(signal_id: str) -> RowLoad:
    path = _db_path()
    if not path or not Path(path).is_file():
        return "missing_db"
    try:
        import duckdb
    except ImportError:
        _emit(
            {"status": "error", "message": "duckdb no instalado (pip install duckdb)"},
            rc=1,
        )
    con = duckdb.connect(path, read_only=True)
    try:
        rows = con.execute(
            """
            SELECT ticker, signal_type, proposed_weight
            FROM finance_worker.trade_signals
            WHERE CAST(signal_id AS VARCHAR) = ?
            LIMIT 1
            """,
            [signal_id.strip().lower()],
        ).fetchall()
    finally:
        con.close()
    if not rows:
        return "not_found"
    tkr = str(rows[0][0] or "").strip().upper()
    st = str(rows[0][1] or "ENTRY").strip().upper()
    try:
        w = float(rows[0][2] or 0.0)
    except (TypeError, ValueError):
        w = 0.0
    return (tkr, st, w)


def _plan_from_embedded() -> _WeightPlan | _SharesPlan | None:
    raw = (os.environ.get("DUCKCLAW_EMBEDDED_EXECUTE_JSON") or "").strip()
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return None
    mode = str(d.get("mode") or "").strip().lower()
    tkr = str(d.get("ticker") or "").strip().upper()
    if not tkr:
        return None
    if mode == "shares":
        act = str(d.get("action") or "").strip().upper()
        try:
            q = float(d["quantity"])
        except (KeyError, TypeError, ValueError):
            return None
        if q <= 0 or act not in ("BUY", "SELL"):
            return None
        return _SharesPlan(ticker=tkr, action=act, quantity=q)
    if mode == "weight":
        try:
            w = float(d["proposed_weight"])
        except (KeyError, TypeError, ValueError):
            return None
        if w <= 0:
            return None
        st = str(d.get("signal_type") or "ENTRY").strip().upper()
        if st not in ("ENTRY", "EXIT"):
            st = "ENTRY"
        return _WeightPlan(ticker=tkr, signal_type=st, weight_pct=w)
    return None


def _plan_from_db(signal_id: str) -> _WeightPlan | None:
    row = _load_signal_row(signal_id)
    if row == "missing_db":
        _emit(
            {
                "status": "error",
                "message": (
                    "Sin DUCKCLAW_EMBEDDED_EXECUTE_JSON y sin IBKR_EXECUTE_ORDER_DB_PATH válido "
                    "(o copia local de la bóveda)."
                ),
            },
            rc=1,
        )
    if row == "not_found":
        _emit(
            {"status": "error", "message": f"No hay fila en trade_signals para signal_id={signal_id}"},
            rc=1,
        )
    tkr, st, w = row
    if not tkr:
        _emit({"status": "error", "message": "Señal sin ticker"}, rc=1)
    if w <= 0:
        _emit({"status": "error", "message": "proposed_weight debe ser > 0"}, rc=1)
    return _WeightPlan(ticker=tkr, signal_type=st, weight_pct=w)


def _resolve_plan(signal_id: str) -> _WeightPlan | _SharesPlan:
    emb = _plan_from_embedded()
    if emb is not None:
        return emb
    w = _plan_from_db(signal_id)
    assert w is not None
    return w


def _ib_port_for_paper(use_paper: bool) -> int:
    if use_paper:
        raw = (os.environ.get("IB_PORT_PAPER") or os.environ.get("IB_PORT") or "").strip()
    else:
        raw = (os.environ.get("IB_PORT_LIVE") or os.environ.get("IB_PORT") or "").strip()
    if raw:
        try:
            p = int(raw)
            if p > 0:
                return p
        except ValueError:
            pass
    if use_paper:
        return 4002
    return 4001


def _client_id() -> int:
    raw = (
        os.environ.get("BROKER_EXECUTE_CLIENT_ID")
        or os.environ.get("IB_CLIENT_ID")
        or "47"
    ).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 47


def _max_notional() -> float | None:
    raw = (os.environ.get("IBKR_EXECUTE_MAX_NOTIONAL_USD") or "").strip()
    if not raw:
        return None
    try:
        v = float(raw)
        return v if v > 0 else None
    except ValueError:
        return None


async def _net_liquidation_usd(ib: Any) -> float | None:
    try:
        ib.reqAccountSummary()
        await asyncio.sleep(1.0)
        for av in ib.accountSummary():
            if getattr(av, "tag", None) != "NetLiquidation":
                continue
            cur = str(getattr(av, "currency", "") or "")
            if cur not in ("USD", "BASE"):
                continue
            try:
                return float(av.value)
            except (TypeError, ValueError):
                continue
    except Exception:
        return None
    return None


def _ticker_scalar_px(val: Any) -> float | None:
    """ib_async a veces expone ``close``/otros como método; no usar float() sobre eso."""
    if val is None or callable(val):
        return None
    try:
        x = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or x <= 0:
        return None
    return x


async def _ref_price(ib: Any, contract: Any) -> float | None:
    ib.reqMktData(contract, "", False, False)
    try:
        await asyncio.sleep(1.25)
        t = ib.ticker(contract)
        if t is None:
            return None
        for attr in ("marketPrice", "last", "close"):
            px = _ticker_scalar_px(getattr(t, attr, None))
            if px is not None:
                return px
        bid = _ticker_scalar_px(getattr(t, "bid", None))
        ask = _ticker_scalar_px(getattr(t, "ask", None))
        if bid is not None and ask is not None:
            return (bid + ask) / 2.0
        return None
    finally:
        try:
            ib.cancelMktData(contract)
        except Exception:
            pass


async def _position_qty(ib: Any, ticker: str) -> float:
    total = 0.0
    try:
        for p in ib.positions():
            c = getattr(p, "contract", None)
            sym = getattr(c, "symbol", None) if c is not None else None
            if sym and str(sym).upper() == ticker.upper():
                total += float(getattr(p, "position", 0) or 0)
    except Exception:
        return 0.0
    return total


async def main_async(signal_id: str, use_paper: bool) -> None:
    try:
        from ib_async import IB, MarketOrder, Stock
    except ImportError:
        _emit(
            {"status": "error", "message": "ib_async no instalado; pip install ib_async"},
            rc=1,
        )

    plan = _resolve_plan(signal_id)

    host = (os.environ.get("IB_HOST") or "127.0.0.1").strip()
    port = _ib_port_for_paper(use_paper)
    client_id = _client_id()

    ib = IB()
    try:
        await ib.connectAsync(host, port, clientId=client_id, timeout=45)
    except Exception as exc:
        _emit({"status": "error", "message": f"IB connect failed: {exc!s}"}, rc=1)

    # Error 10089: sin suscripción «real-time» para API, reqMktData falla. Datos retrasados (3) suelen bastar para sizing.
    # 1=live 2=frozen 3=delayed 4=delayed_frozen — ver TWS «Market Data Type».
    _mdt_raw = (os.environ.get("IBKR_MARKET_DATA_TYPE") or "3").strip()
    try:
        _mdt = int(_mdt_raw)
        if 1 <= _mdt <= 4:
            ib.reqMarketDataType(_mdt)
    except (ValueError, TypeError, Exception):
        try:
            ib.reqMarketDataType(3)
        except Exception:
            pass

    try:
        if isinstance(plan, _SharesPlan):
            ticker = plan.ticker
            action = plan.action
            qty = max(1, int(plan.quantity))
            if action == "SELL":
                pos = await _position_qty(ib, ticker)
                if pos <= 0:
                    _emit(
                        {"status": "error", "message": f"SELL sin posición larga en {ticker}"},
                        rc=1,
                    )
                qty = min(qty, int(abs(pos)))
            contract = Stock(ticker, "SMART", "USD")
            await ib.qualifyContractsAsync(contract)
            order = MarketOrder(action, qty)
            trade = ib.placeOrder(contract, order)
            await asyncio.sleep(0.5)
            oid = None
            if trade and getattr(trade, "order", None):
                oid = getattr(trade.order, "orderId", None)
            _emit(
                {
                    "status": "success",
                    "ticker": ticker,
                    "action": action,
                    "qty": qty,
                    "mode": "shares",
                    "paper": use_paper,
                    "ib_order_id": oid,
                },
                rc=0,
            )
            return

        ticker = plan.ticker
        signal_type = plan.signal_type
        weight_pct = plan.weight_pct
        contract = Stock(ticker, "SMART", "USD")
        await ib.qualifyContractsAsync(contract)

        equity_env = (os.environ.get("IBKR_EXECUTE_ACCOUNT_EQUITY_USD") or "").strip()
        equity: float | None = None
        if equity_env:
            try:
                equity = float(equity_env)
            except ValueError:
                equity = None
        if equity is None or equity <= 0:
            equity = await _net_liquidation_usd(ib)
        if equity is None or equity <= 0:
            _emit(
                {
                    "status": "error",
                    "message": "Sin NetLiquidation USD; defina IBKR_EXECUTE_ACCOUNT_EQUITY_USD",
                },
                rc=1,
            )

        notional = equity * (weight_pct / 100.0)
        cap = _max_notional()
        if cap is not None:
            notional = min(notional, cap)

        price = await _ref_price(ib, contract)
        if price is None or price <= 0:
            _emit({"status": "error", "message": f"No se obtuvo precio para {ticker}"}, rc=1)

        qty_float = notional / price
        qty = max(1, int(qty_float))

        is_entry = signal_type != "EXIT"
        action = "BUY" if is_entry else "SELL"

        if not is_entry:
            pos = await _position_qty(ib, ticker)
            if pos <= 0:
                _emit(
                    {"status": "error", "message": f"EXIT sin posición larga en {ticker}"},
                    rc=1,
                )
            qty = min(qty, int(abs(pos)))

        order = MarketOrder(action, qty)
        trade = ib.placeOrder(contract, order)
        await asyncio.sleep(0.5)

        oid = None
        if trade and getattr(trade, "order", None):
            oid = getattr(trade.order, "orderId", None)

        _emit(
            {
                "status": "success",
                "ticker": ticker,
                "action": action,
                "qty": qty,
                "signal_type": signal_type,
                "mode": "weight",
                "paper": use_paper,
                "notional_usd": round(notional, 2),
                "ref_price": round(price, 4),
                "ib_order_id": oid,
            },
            rc=0,
        )
    except Exception as exc:
        _emit({"status": "error", "message": f"order_failed: {exc!s}"}, rc=1)
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass


def main() -> None:
    if len(sys.argv) < 3:
        _emit(
            {
                "status": "error",
                "message": "Uso: broker_execute_signal.py <signal_id> <paper 1|0>",
            },
            rc=1,
        )
    sid = sys.argv[1].strip()
    pflag = sys.argv[2].strip()
    use_paper = pflag == "1"
    asyncio.run(main_async(sid, use_paper))


if __name__ == "__main__":
    main()
