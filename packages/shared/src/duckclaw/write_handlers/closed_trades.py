"""Closed-trades write handlers — insert into quant_core.closed_trades."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from duckclaw.write_handlers.registry import register_handler

_log = logging.getLogger(__name__)


def _ensure_closed_trades_schema(conn: Any) -> None:
    """Ensure quant_core.closed_trades exists (migration v40 / ensure helper)."""
    try:
        conn.execute(
            "SELECT COUNT(*) FROM quant_core.closed_trades LIMIT 1"
        ).fetchone()
    except Exception:
        _log.warning(
            "quant_core.closed_trades not found — run duckclaw-migrate (v40) "
            "or ensure_closed_trades_schema(vault_path)"
        )
        raise RuntimeError(
            "Tabla quant_core.closed_trades no existe — correr migraciones"
        )


def _parse_signal_uuid(raw: Any) -> str | None:
    sid = str(raw or "").strip()
    if not sid:
        return None
    try:
        return str(uuid.UUID(sid))
    except ValueError:
        return None


def _apply_insert_closed_trade(conn: Any, payload: dict) -> None:
    """Insert closed trade; idempotent on (ticker, closed_at, qty, fill_id)."""
    _ensure_closed_trades_schema(conn)

    ticker = str(payload["ticker"]).strip().upper()
    fill_id = str(payload["fill_id"]).strip()
    closed_at = str(payload["closed_at"]).strip()
    qty = float(payload["qty"])
    entry_px = float(payload["entry_px"])
    exit_px = float(payload["exit_px"])
    pnl = float(payload["pnl"])
    ret_pct = float(payload["ret_pct"])
    side = str(payload["side"]).strip().upper()
    session_uid = str(payload.get("session_uid") or "").strip() or None
    signal_id = _parse_signal_uuid(payload.get("signal_id"))

    if not ticker or not fill_id:
        raise ValueError("insert_closed_trade: ticker y fill_id requeridos")
    if side not in ("LONG", "SHORT"):
        raise ValueError(f"insert_closed_trade: side inválido: {side}")
    if entry_px <= 0 or exit_px <= 0:
        raise ValueError("insert_closed_trade: entry_px/exit_px deben ser > 0")

    conn.execute(
        """
        INSERT INTO quant_core.closed_trades (
            signal_id,
            session_uid,
            ticker,
            closed_at,
            pnl,
            ret_pct,
            qty,
            entry_px,
            exit_px,
            side,
            fill_id
        ) VALUES (
            ?::UUID, ?, ?, ?::TIMESTAMP, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT (ticker, closed_at, qty, fill_id) DO NOTHING
        """,
        [
            signal_id,
            session_uid,
            ticker,
            closed_at,
            pnl,
            ret_pct,
            qty,
            entry_px,
            exit_px,
            side,
            fill_id,
        ],
    )

    _log.info(
        "closed_trade inserted: %s %s qty=%s fill_id=%s pnl=%s",
        side,
        ticker,
        qty,
        fill_id[:64],
        pnl,
    )


register_handler("insert_closed_trade", _apply_insert_closed_trade)
