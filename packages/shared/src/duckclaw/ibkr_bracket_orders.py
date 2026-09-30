"""IBKR Bracket Orders — entrada + TP + SL automático.

Envía órdenes bracket (main + take-profit + stop-loss) a Interactive Brokers
usando ib_insync. Las órdenes TP/SL se ejecutan automáticamente en el broker
cuando el precio alcanza los niveles configurados.

Motivation:
    Manual TP/SL monitoring in tp_sl_levels sin ejecución automática causó
    pérdida de $32,400 en CEG (TP $300 alcanzado a $305.80 pero posición no cerrada).

Architecture:
    - Bracket orders: 3 órdenes ligadas (main + TP + SL) en OCA group
    - GTC (Good Till Canceled): TP/SL activos 24/7 en el broker
    - Auto-cancel: si ejecuta TP → cancela SL, y viceversa

Usage::

    from duckclaw.ibkr_bracket_orders import (
        create_bracket_order,
        submit_bracket_order,
        connect_ibkr,
    )

    # Conectar a IBKR Gateway/TWS
    ib = await connect_ibkr()

    # Crear bracket order
    main, tp, sl = create_bracket_order(
        ticker="CEG",
        side="BUY",
        quantity=994,
        tp_price=300.0,
        sl_price=245.0,
    )

    # Enviar al broker
    result = await submit_bracket_order(ib, "CEG", "BUY", 994, 300.0, 245.0)
    # → {"main_order_id": 123, "tp_order_id": 124, "sl_order_id": 125}

    await ib.disconnect()

Environment Variables:
    IBKR_HOST: IP/hostname del Gateway/TWS (default: 127.0.0.1)
    IBKR_PORT: Puerto (paper: 4002, live: 4001)
    IBKR_CLIENT_ID: Client ID único (default: 1)

ponytail: Solo env vars para config. No auto-retry en connect (caller debe
manejar timeout/reconnect). Bracket order validation es basic (price sanity)
— el broker hace la validación final.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

_log = logging.getLogger(__name__)

# ib_insync es optional dependency — solo importar cuando se usa realmente
_IB_INSYNC_AVAILABLE = False
try:
    try:
        asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    from ib_insync import IB, LimitOrder, MarketOrder, Stock, StopLimitOrder

    _IB_INSYNC_AVAILABLE = True
except ImportError:
    _log.warning(
        "ib_insync no disponible — instalar con: uv pip install ib-insync"
    )


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


async def connect_ibkr(
    host: str | None = None,
    port: int | None = None,
    client_id: int | None = None,
) -> "IB":
    """Conecta a IBKR Gateway o TWS.

    Args:
        host: IP/hostname (default: IBKR_HOST env var o 127.0.0.1)
        port: Puerto (default: IBKR_PORT env var o 4002 paper)
        client_id: Client ID único (default: IBKR_CLIENT_ID env var o 1; monitor usa IBKR_MONITOR_CLIENT_ID)

    Returns:
        IB: Cliente conectado de ib_insync

    Raises:
        ImportError: Si ib_insync no está instalado
        ConnectionError: Si no puede conectar al Gateway/TWS
    """
    if not _IB_INSYNC_AVAILABLE:
        raise ImportError(
            "ib_insync no disponible — instalar con: uv pip install ib-insync"
        )

    host = host or os.getenv("IBKR_HOST", "127.0.0.1")
    port = port or int(os.getenv("IBKR_PORT", "4002"))
    client_id = client_id or int(os.getenv("IBKR_CLIENT_ID", "1"))

    ib = IB()
    try:
        await ib.connectAsync(host, port, clientId=client_id, timeout=10)
        _log.info(f"Conectado a IBKR Gateway: {host}:{port} (client_id={client_id})")
        return ib
    except Exception as exc:
        _log.error(f"Error conectando a IBKR {host}:{port}: {exc}")
        raise ConnectionError(f"No se pudo conectar a IBKR Gateway: {exc}") from exc


# ---------------------------------------------------------------------------
# Bracket Order Creation
# ---------------------------------------------------------------------------


def _stop_loss_order(close_action: str, quantity: int, sl_price: float) -> "StopLimitOrder":
    """SL as STP LMT: IBKR drops outsideRth on plain STP for US stocks, so a
    plain stop can't trigger pre/post-market (e.g. an earnings gap AfterClose).

    The limit sits ``IBKR_SL_LIMIT_OFFSET_PCT`` (default 5%) past the stop in the
    closing direction. ponytail: a gap beyond that band leaves the SL unfilled
    (resting limit) instead of selling at any price; widen the env knob to trade
    fill-certainty for slippage.
    """
    pct = float(os.getenv("IBKR_SL_LIMIT_OFFSET_PCT", "5")) / 100.0
    sign = -1.0 if close_action == "SELL" else 1.0
    lmt = round(sl_price * (1.0 + sign * pct), 2)
    order = StopLimitOrder(close_action, quantity, lmt, sl_price)
    order.tif = "GTC"
    order.outsideRth = True
    return order



def create_bracket_order(
    ticker: str,
    side: str,
    quantity: int,
    tp_price: Optional[float] = None,
    sl_price: Optional[float] = None,
) -> tuple["MarketOrder", Optional["LimitOrder"], Optional["StopLimitOrder"]]:
    """Crea bracket order (entrada + TP + SL).

    Args:
        ticker: Símbolo del instrumento (ej: "CEG", "SPY")
        side: "BUY" o "SELL"
        quantity: Cantidad de shares/contratos
        tp_price: Precio de take profit (limit order)
        sl_price: Precio de stop loss (stop order)

    Returns:
        (main_order, tp_order, sl_order)
        Si tp_price o sl_price es None, esa orden será None

    Raises:
        ValueError: Si side inválido, quantity <= 0, o precios inválidos
        ImportError: Si ib_insync no está instalado

    Example:
        >>> main, tp, sl = create_bracket_order("CEG", "BUY", 994, 300.0, 245.0)
        >>> main.action
        'BUY'
        >>> tp.lmtPrice
        300.0
        >>> sl.auxPrice
        245.0
    """
    if not _IB_INSYNC_AVAILABLE:
        raise ImportError(
            "ib_insync no disponible — instalar con: uv pip install ib-insync"
        )

    # Validación básica
    if side not in ("BUY", "SELL"):
        raise ValueError(f"side debe ser 'BUY' o 'SELL', got: {side}")

    if quantity <= 0:
        raise ValueError(f"quantity debe ser > 0, got: {quantity}")

    if not ticker or not ticker.strip():
        raise ValueError("ticker no puede estar vacío")

    if tp_price is not None and tp_price <= 0:
        raise ValueError(f"tp_price debe ser > 0, got: {tp_price}")
    if sl_price is not None and sl_price <= 0:
        raise ValueError(f"sl_price debe ser > 0, got: {sl_price}")

    # Dirección: BUY => TP > SL; SELL => TP < SL (cuando ambos presentes)
    if tp_price is not None and sl_price is not None:
        if side == "BUY" and not (tp_price > sl_price):
            raise ValueError(
                f"BUY requiere tp_price > sl_price, got tp={tp_price} sl={sl_price}"
            )
        if side == "SELL" and not (tp_price < sl_price):
            raise ValueError(
                f"SELL requiere tp_price < sl_price, got tp={tp_price} sl={sl_price}"
            )

    # Main order (market)
    main = MarketOrder(side, quantity)
    main.outsideRth = True  # Permite ejecución fuera de horario regular
    main.transmit = False  # No enviar aún (primero crear TP/SL)

    # Si no hay TP/SL, solo retornar main order
    if tp_price is None and sl_price is None:
        main.transmit = True
        return (main, None, None)

    # Acción opuesta para cerrar posición
    close_action = "SELL" if side == "BUY" else "BUY"

    # Take Profit (limit order)
    tp_order = None
    if tp_price is not None:
        tp_order = LimitOrder(close_action, quantity, tp_price)
        tp_order.parentId = main.orderId
        tp_order.transmit = False  # Parte del grupo OCA
        tp_order.tif = "GTC"  # Good Till Canceled
        tp_order.outsideRth = True

    # Stop Loss (stop order)
    sl_order = None
    if sl_price is not None:
        sl_order = _stop_loss_order(close_action, quantity, sl_price)
        sl_order.parentId = main.orderId
        # Solo el último en el grupo tiene transmit=True para enviar todo junto
        sl_order.transmit = True if tp_order is None else False

    # Si solo hay TP (sin SL), TP debe tener transmit=True
    if tp_order and not sl_order:
        tp_order.transmit = True

    # Si hay ambos, SL es el último y debe tener transmit=True
    if tp_order and sl_order:
        sl_order.transmit = True
        # OCA: si llena TP cancela SL y viceversa (belt-and-suspenders con parentId)
        oca = f"BRACKET_{ticker.strip().upper()}"
        tp_order.ocaGroup = oca
        tp_order.ocaType = 1  # Cancel with block
        sl_order.ocaGroup = oca
        sl_order.ocaType = 1

    return (main, tp_order, sl_order)


# ---------------------------------------------------------------------------
# Bracket Order Submission
# ---------------------------------------------------------------------------


async def submit_bracket_order(
    ib: "IB",
    ticker: str,
    side: str,
    quantity: int,
    tp_price: Optional[float] = None,
    sl_price: Optional[float] = None,
    exchange: str = "SMART",
    currency: str = "USD",
) -> dict:
    """Envía bracket order a IBKR.

    Args:
        ib: Cliente IB conectado (de connect_ibkr)
        ticker: Símbolo del instrumento
        side: "BUY" o "SELL"
        quantity: Cantidad de shares/contratos
        tp_price: Precio de take profit (opcional)
        sl_price: Precio de stop loss (opcional)
        exchange: Exchange (default: SMART routing)
        currency: Moneda (default: USD)

    Returns:
        {
            "main_order_id": int,
            "tp_order_id": Optional[int],
            "sl_order_id": Optional[int],
            "status": "submitted",
            "timestamp": datetime (UTC),
            "ticker": str,
            "side": str,
            "quantity": int,
        }

    Raises:
        ValueError: Si argumentos inválidos
        RuntimeError: Si error al enviar al broker
        ImportError: Si ib_insync no está instalado

    Example:
        >>> ib = await connect_ibkr()
        >>> result = await submit_bracket_order(
        ...     ib, "CEG", "BUY", 994, tp_price=300.0, sl_price=245.0
        ... )
        >>> result["main_order_id"]
        12345
        >>> await ib.disconnect()
    """
    if not _IB_INSYNC_AVAILABLE:
        raise ImportError(
            "ib_insync no disponible — instalar con: uv pip install ib-insync"
        )

    # Crear contrato
    contract = Stock(ticker, exchange, currency)

    # Crear órdenes
    main, tp, sl = create_bracket_order(ticker, side, quantity, tp_price, sl_price)

    # Enviar main order
    try:
        main_trade = ib.placeOrder(contract, main)
        _log.info(
            f"Orden principal enviada: {side} {quantity} {ticker} @ market "
            f"(order_id={main_trade.order.orderId})"
        )
    except Exception as exc:
        _log.error(f"Error enviando orden principal {ticker}: {exc}")
        raise RuntimeError(f"Error enviando orden principal: {exc}") from exc

    # Enviar TP (si existe)
    tp_trade = None
    if tp:
        try:
            tp.parentId = main_trade.order.orderId
            if sl is not None:
                oca = f"BRACKET_{ticker.strip().upper()}_{main_trade.order.orderId}"
                tp.ocaGroup = oca
                tp.ocaType = 1
            tp_trade = ib.placeOrder(contract, tp)
            _log.info(
                f"Orden TP enviada: {tp.action} {quantity} {ticker} @ limit {tp_price} "
                f"(order_id={tp_trade.order.orderId})"
            )
        except Exception as exc:
            _log.error(f"Error enviando orden TP {ticker}: {exc}")
            # Intentar cancelar main order
            try:
                ib.cancelOrder(main_trade.order)
                _log.warning(f"Main order {main_trade.order.orderId} cancelada tras error TP")
            except Exception:
                pass
            raise RuntimeError(f"Error enviando orden TP: {exc}") from exc

    # Enviar SL (si existe)
    sl_trade = None
    if sl:
        try:
            sl.parentId = main_trade.order.orderId
            if tp is not None:
                oca = f"BRACKET_{ticker.strip().upper()}_{main_trade.order.orderId}"
                sl.ocaGroup = oca
                sl.ocaType = 1
            sl_trade = ib.placeOrder(contract, sl)
            _log.info(
                f"Orden SL enviada: {sl.action} {quantity} {ticker} @ stop {sl_price} "
                f"(order_id={sl_trade.order.orderId})"
            )
        except Exception as exc:
            _log.error(f"Error enviando orden SL {ticker}: {exc}")
            # Intentar cancelar main y tp
            try:
                ib.cancelOrder(main_trade.order)
                if tp_trade:
                    ib.cancelOrder(tp_trade.order)
                _log.warning(
                    f"Orders canceladas tras error SL: main={main_trade.order.orderId}, "
                    f"tp={tp_trade.order.orderId if tp_trade else None}"
                )
            except Exception:
                pass
            raise RuntimeError(f"Error enviando orden SL: {exc}") from exc

    # Esperar confirmación de envío
    # ib.sleep() (sync, blocks via loop.run_until_complete) reenters the already-
    # running loop and raises "This event loop is already running" from inside
    # this coroutine — uncaught here, which would mask an actually-successful
    # submission (orders already placed above) as a failure. asyncio.sleep() is
    # the correct async-context equivalent.
    await asyncio.sleep(1)

    result = {
        "main_order_id": main_trade.order.orderId,
        "tp_order_id": tp_trade.order.orderId if tp_trade else None,
        "sl_order_id": sl_trade.order.orderId if sl_trade else None,
        "status": "submitted",
        "timestamp": datetime.now(timezone.utc),
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
    }

    _log.info(
        f"Bracket order enviado: {ticker} {side} {quantity} — "
        f"main={result['main_order_id']}, tp={result['tp_order_id']}, sl={result['sl_order_id']}"
    )

    return result


# ---------------------------------------------------------------------------
# Protective TP/SL for EXISTING positions (no new entry)
# ---------------------------------------------------------------------------


def create_protective_oca_orders(
    *,
    ticker: str,
    position_side: str,
    quantity: int,
    tp_price: Optional[float] = None,
    sl_price: Optional[float] = None,
) -> tuple[Optional["LimitOrder"], Optional["StopLimitOrder"]]:
    """Crea TP/SL GTC en OCA para una posición ya abierta (sin market entry).

    Args:
        position_side: "BUY" (long) o "SELL" (short) — dirección de la posición abierta.
    """
    if not _IB_INSYNC_AVAILABLE:
        raise ImportError(
            "ib_insync no disponible — instalar con: uv pip install ib-insync"
        )
    side = (position_side or "").strip().upper()
    if side not in ("BUY", "SELL"):
        raise ValueError(f"position_side debe ser 'BUY' o 'SELL', got: {position_side}")
    if quantity <= 0:
        raise ValueError(f"quantity debe ser > 0, got: {quantity}")
    if tp_price is None and sl_price is None:
        raise ValueError("se requiere al menos tp_price o sl_price")
    if tp_price is not None and tp_price <= 0:
        raise ValueError(f"tp_price debe ser > 0, got: {tp_price}")
    if sl_price is not None and sl_price <= 0:
        raise ValueError(f"sl_price debe ser > 0, got: {sl_price}")
    if tp_price is not None and sl_price is not None:
        if side == "BUY" and not (tp_price > sl_price):
            raise ValueError(
                f"long requiere tp_price > sl_price, got tp={tp_price} sl={sl_price}"
            )
        if side == "SELL" and not (tp_price < sl_price):
            raise ValueError(
                f"short requiere tp_price < sl_price, got tp={tp_price} sl={sl_price}"
            )

    close_action = "SELL" if side == "BUY" else "BUY"
    oca = f"PROTECT_{ticker.strip().upper()}"

    tp_order = None
    if tp_price is not None:
        tp_order = LimitOrder(close_action, quantity, tp_price)
        tp_order.tif = "GTC"
        tp_order.outsideRth = True
        tp_order.transmit = False
        tp_order.ocaGroup = oca
        tp_order.ocaType = 1

    sl_order = None
    if sl_price is not None:
        sl_order = _stop_loss_order(close_action, quantity, sl_price)
        sl_order.transmit = False
        sl_order.ocaGroup = oca
        sl_order.ocaType = 1

    # Última orden del grupo transmite ambas (OCA). For protective pairs without a
    # parent market order, both must transmit=True — otherwise placeOrder(TP) with
    # transmit=False is held and never flushed when SL is a separate placeOrder.
    if tp_order is not None:
        tp_order.transmit = True
    if sl_order is not None:
        sl_order.transmit = True

    return (tp_order, sl_order)


async def cancel_protective_orders_for_ticker(
    ib: "IB",
    ticker: str,
    *,
    oca_prefix: str = "PROTECT_",
) -> int:
    """Cancel open protective/OCA orders for ``ticker`` (best-effort).

    Matches by symbol and optional OCA group prefix (default ``PROTECT_``).
    Also cancels unmatched open LMT/STP closes on the same symbol so qty
    realignment does not leave duplicate working brackets.
    """
    if not _IB_INSYNC_AVAILABLE:
        raise ImportError(
            "ib_insync no disponible — instalar con: uv pip install ib-insync"
        )
    sym = (ticker or "").strip().upper()
    if not sym:
        return 0
    prefix = (oca_prefix or "").upper()
    cancelled = 0
    try:
        # Cross-client working orders (protective scripts use ephemeral client ids).
        try:
            # reqAllOpenOrders() (sync) blocks via loop.run_until_complete() and
            # raises "This event loop is already running" from inside this
            # coroutine — reqAllOpenOrdersAsync() is the async-context equivalent.
            await ib.reqAllOpenOrdersAsync()
            await asyncio.sleep(0.8)
        except Exception as exc:
            _log.warning("reqAllOpenOrders before cancel %s: %s", sym, exc)
        trades = list(ib.openTrades() or [])
    except Exception as exc:
        _log.warning("openTrades failed before cancel %s: %s", sym, exc)
        return 0
    for trade in trades:
        c = getattr(trade, "contract", None)
        o = getattr(trade, "order", None)
        if c is None or o is None:
            continue
        if str(getattr(c, "symbol", "") or "").strip().upper() != sym:
            continue
        oca = str(getattr(o, "ocaGroup", "") or "").upper()
        otype = str(getattr(o, "orderType", "") or "").upper()
        if prefix and oca.startswith(prefix):
            pass
        elif otype in ("LMT", "STP", "STP LMT", "TRAIL"):
            pass
        else:
            continue
        try:
            ib.cancelOrder(o)
            cancelled += 1
        except Exception as exc:
            _log.warning(
                "cancelOrder failed %s id=%s: %s",
                sym,
                getattr(o, "orderId", None),
                exc,
            )
    if cancelled:
        await asyncio.sleep(0.5)
    return cancelled


async def cancel_open_orders(
    ib: "IB",
    *,
    ticker: str | None = None,
    order_ids: list[int] | None = None,
    dry_run: bool = False,
) -> dict:
    """Cancel matching open IBKR orders by ticker and/or order id.

    This is the explicit operator/tool path. ``cancel_protective_orders_for_ticker``
    remains the replacement helper used by protective OCA placement.
    """
    if not _IB_INSYNC_AVAILABLE:
        raise ImportError(
            "ib_insync no disponible — instalar con: uv pip install ib-insync"
        )
    sym = (ticker or "").strip().upper()
    ids = {int(x) for x in (order_ids or []) if int(x) > 0}
    if not sym and not ids:
        raise ValueError("se requiere ticker o al menos un order_id")

    try:
        try:
            await ib.reqAllOpenOrdersAsync()
            await asyncio.sleep(0.8)
        except Exception as exc:
            _log.warning("reqAllOpenOrders before explicit cancel: %s", exc)
        trades = list(ib.openTrades() or [])
    except Exception as exc:
        raise RuntimeError(f"openTrades failed before explicit cancel: {exc}") from exc

    matched = []
    cancelled = []
    for trade in trades:
        c = getattr(trade, "contract", None)
        o = getattr(trade, "order", None)
        if c is None or o is None:
            continue
        oid = int(getattr(o, "orderId", 0) or 0)
        tsym = str(getattr(c, "symbol", "") or "").strip().upper()
        if ids and oid not in ids:
            continue
        if sym and tsym != sym:
            continue
        row = {
            "order_id": oid,
            "ticker": tsym,
            "action": getattr(o, "action", None),
            "order_type": getattr(o, "orderType", None),
            "quantity": float(getattr(o, "totalQuantity", 0) or 0),
            "oca_group": getattr(o, "ocaGroup", None),
        }
        matched.append(row)
        if dry_run:
            continue
        try:
            ib.cancelOrder(o)
            cancelled.append(row)
        except Exception as exc:
            row["error"] = str(exc)

    if cancelled:
        await asyncio.sleep(1.0)
    return {
        "status": "success",
        "dry_run": dry_run,
        "matched_count": len(matched),
        "cancelled_count": len(cancelled),
        "matched": matched,
        "cancelled": cancelled,
    }


async def submit_protective_oca_orders(
    ib: "IB",
    ticker: str,
    position_side: str,
    quantity: int,
    tp_price: Optional[float] = None,
    sl_price: Optional[float] = None,
    exchange: str = "SMART",
    currency: str = "USD",
    *,
    cancel_existing: bool = False,
) -> dict:
    """Coloca TP/SL GTC protectivos para una posición existente (sin nueva entrada)."""
    if not _IB_INSYNC_AVAILABLE:
        raise ImportError(
            "ib_insync no disponible — instalar con: uv pip install ib-insync"
        )

    if cancel_existing:
        n = await cancel_protective_orders_for_ticker(ib, ticker)
        if n:
            _log.info("Cancelled %s existing open order(s) for %s before protective place", n, ticker)

    contract = Stock(ticker, exchange, currency)
    tp, sl = create_protective_oca_orders(
        ticker=ticker,
        position_side=position_side,
        quantity=quantity,
        tp_price=tp_price,
        sl_price=sl_price,
    )

    # Qualify contract so SMART resolves before placeOrder
    try:
        await ib.qualifyContractsAsync(contract)
    except Exception as exc:
        _log.warning("qualifyContracts %s: %s (continuando)", ticker, exc)

    # Unique OCA per place so replace cycles do not collide with stale broker groups.
    oca = f"PROTECT_{ticker.strip().upper()}_{int(datetime.now(timezone.utc).timestamp())}"
    tp_trade = None
    sl_trade = None
    try:
        if tp is not None:
            tp.ocaGroup = oca
            tp_trade = ib.placeOrder(contract, tp)
            _log.info(
                "Protective TP: %s %s %s @ LMT %s (id=%s)",
                tp.action,
                quantity,
                ticker,
                tp_price,
                tp_trade.order.orderId,
            )
        if sl is not None:
            sl.ocaGroup = oca
            sl_trade = ib.placeOrder(contract, sl)
            _log.info(
                "Protective SL: %s %s %s @ STP %s (id=%s)",
                sl.action,
                quantity,
                ticker,
                sl_price,
                sl_trade.order.orderId,
            )
    except Exception as exc:
        for trade in (tp_trade, sl_trade):
            if trade is not None:
                try:
                    ib.cancelOrder(trade.order)
                except Exception:
                    pass
        raise RuntimeError(f"Error enviando protective OCA {ticker}: {exc}") from exc

    await asyncio.sleep(1)
    result = {
        "main_order_id": None,
        "tp_order_id": tp_trade.order.orderId if tp_trade else None,
        "sl_order_id": sl_trade.order.orderId if sl_trade else None,
        "status": "submitted",
        "timestamp": datetime.now(timezone.utc),
        "ticker": ticker,
        "side": position_side.strip().upper(),
        "quantity": quantity,
        "oca_group": oca,
        "tp_price": tp_price,
        "sl_price": sl_price,
    }
    _log.info(
        "Protective OCA enviado: %s qty=%s tp=%s sl=%s",
        ticker,
        quantity,
        result["tp_order_id"],
        result["sl_order_id"],
    )
    return result


# ---------------------------------------------------------------------------
# Order Status Query (helper)
# ---------------------------------------------------------------------------


async def get_order_status(ib: "IB", order_id: int) -> dict | None:
    """Consulta estado de una orden por ID.

    Args:
        ib: Cliente IB conectado
        order_id: ID de la orden

    Returns:
        {
            "order_id": int,
            "status": str,  # "Submitted", "Filled", "Cancelled", etc
            "filled_qty": float,
            "filled_price": float,
            "remaining_qty": float,
        }
        o None si la orden no se encuentra

    Example:
        >>> status = await get_order_status(ib, 12345)
        >>> status["status"]
        'Filled'
    """
    if not _IB_INSYNC_AVAILABLE:
        raise ImportError("ib_insync no disponible")

    trades = ib.trades()
    for trade in trades:
        if trade.order.orderId == order_id:
            return {
                "order_id": order_id,
                "status": trade.orderStatus.status,
                "filled_qty": trade.orderStatus.filled,
                "filled_price": trade.orderStatus.avgFillPrice,
                "remaining_qty": trade.orderStatus.remaining,
            }

    return None
