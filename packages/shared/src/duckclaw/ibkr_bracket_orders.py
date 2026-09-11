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

import logging
import os
from datetime import datetime, timezone
from typing import Optional

_log = logging.getLogger(__name__)

# ib_insync es optional dependency — solo importar cuando se usa realmente
_IB_INSYNC_AVAILABLE = False
try:
    from ib_insync import IB, LimitOrder, MarketOrder, Stock, StopOrder

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


def create_bracket_order(
    ticker: str,
    side: str,
    quantity: int,
    tp_price: Optional[float] = None,
    sl_price: Optional[float] = None,
) -> tuple["MarketOrder", Optional["LimitOrder"], Optional["StopOrder"]]:
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
        sl_order = StopOrder(close_action, quantity, sl_price)
        sl_order.parentId = main.orderId
        # Solo el último en el grupo tiene transmit=True para enviar todo junto
        sl_order.transmit = True if tp_order is None else False
        sl_order.tif = "GTC"
        sl_order.outsideRth = True

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
    await ib.sleep(1)

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
