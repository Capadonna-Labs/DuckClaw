"""IBKR orders write handlers — insert & update orders in quant_core.ibkr_orders."""

from __future__ import annotations

import logging
from typing import Any

from duckclaw.write_handlers.registry import register_handler

_log = logging.getLogger(__name__)


def _ensure_ibkr_orders_schema(conn: Any) -> None:
    """Ensure quant_core.ibkr_orders table exists (should be created by migration v39)."""
    try:
        conn.execute(
            "SELECT COUNT(*) FROM quant_core.ibkr_orders LIMIT 1"
        ).fetchone()
    except Exception:
        _log.warning(
            "quant_core.ibkr_orders not found — run duckclaw-migrate (v39)"
        )
        raise RuntimeError(
            "Tabla quant_core.ibkr_orders no existe — correr migraciones"
        )


def _apply_insert_ibkr_order(conn: Any, payload: dict) -> None:
    """Insert new IBKR order record (idempotent por order_id)."""
    _ensure_ibkr_orders_schema(conn)

    order_id = int(payload["order_id"])
    ticker = str(payload["ticker"])
    side = str(payload["side"])
    quantity = int(payload["quantity"])
    order_type = str(payload["order_type"])
    limit_price = payload.get("limit_price")
    stop_price = payload.get("stop_price")
    parent_order_id = payload.get("parent_order_id")
    status = str(payload.get("status", "submitted"))
    submitted_at = str(payload.get("submitted_at", ""))
    trade_signal_id = str(payload.get("trade_signal_id", ""))
    notes = str(payload.get("notes", ""))

    # INSERT OR REPLACE for idempotency (order_id is PK)
    conn.execute(
        """
        INSERT OR REPLACE INTO quant_core.ibkr_orders (
            order_id,
            ticker,
            side,
            quantity,
            order_type,
            limit_price,
            stop_price,
            parent_order_id,
            status,
            filled_qty,
            filled_price,
            submitted_at,
            filled_at,
            cancelled_at,
            trade_signal_id,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, NULL, NULL, ?, ?)
        """,
        [
            order_id,
            ticker,
            side,
            quantity,
            order_type,
            limit_price,
            stop_price,
            parent_order_id,
            status,
            submitted_at,
            trade_signal_id,
            notes,
        ],
    )

    _log.info(
        f"IBKR order inserted: {order_id} ({side} {quantity} {ticker} @ {order_type})"
    )


def _apply_update_ibkr_order_status(conn: Any, payload: dict) -> None:
    """Update IBKR order status from order monitor (filled, cancelled, etc)."""
    _ensure_ibkr_orders_schema(conn)

    order_id = int(payload["order_id"])
    status = str(payload["status"])
    filled_qty = int(payload.get("filled_qty", 0))
    filled_price = payload.get("filled_price")
    filled_at = str(payload.get("filled_at", ""))
    cancelled_at = str(payload.get("cancelled_at", ""))

    # Build UPDATE query dynamically based on provided fields
    updates = ["status = ?"]
    params = [status]

    if filled_qty > 0:
        updates.append("filled_qty = ?")
        params.append(filled_qty)

    if filled_price is not None:
        updates.append("filled_price = ?")
        params.append(filled_price)

    if filled_at:
        updates.append("filled_at = ?")
        params.append(filled_at)

    if cancelled_at:
        updates.append("cancelled_at = ?")
        params.append(cancelled_at)

    params.append(order_id)

    conn.execute(
        f"""
        UPDATE quant_core.ibkr_orders
        SET {', '.join(updates)}
        WHERE order_id = ?
        """,
        params,
    )

    _log.info(
        f"IBKR order updated: {order_id} → status={status}, filled_qty={filled_qty}"
    )


def _apply_update_trade_signal_executed(conn: Any, payload: dict) -> None:
    """Mark trade signal as executed (update executed_at timestamp)."""
    # Assuming trade_signals table exists in quant_core schema
    signal_id = str(payload["signal_id"])
    executed_at = str(payload.get("executed_at", ""))

    # Check if table exists first
    try:
        conn.execute(
            "SELECT COUNT(*) FROM quant_core.trade_signals LIMIT 1"
        ).fetchone()
    except Exception:
        _log.warning(
            f"quant_core.trade_signals not found — skipping executed_at update for {signal_id}"
        )
        return

    conn.execute(
        """
        UPDATE quant_core.trade_signals
        SET executed_at = ?
        WHERE signal_id = ?
        """,
        [executed_at, signal_id],
    )

    _log.info(f"Trade signal marked as executed: {signal_id} @ {executed_at}")


# Register handlers
register_handler("insert_ibkr_order", _apply_insert_ibkr_order)
register_handler("update_ibkr_order_status", _apply_update_ibkr_order_status)
register_handler("update_trade_signal_executed", _apply_update_trade_signal_executed)
