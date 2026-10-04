"""Signal Execution Bridge — link trade signals → IBKR bracket orders.

Conecta las señales de trading (`trade_signals`, `tp_sl_levels`) con la ejecución
automática de bracket orders en IBKR. Lee los niveles TP/SL configurados y los
envía como órdenes GTC al broker.

Architecture:
    1. Read signal from trade_signals table
    2. Fetch TP/SL levels from tp_sl_levels (ACTIVE)
    3. Create bracket order (main + TP + SL) **or** protective OCA (no entry)
    4. Submit to IBKR Gateway/TWS
    5. Record order_ids in quant_core.ibkr_orders
    6. Update trade_signals.executed_at

``signal_type=BRACKET`` / OCA / PROTECTIVE is **not** a market entry. Those
types must call ``execute_protective_oca_for_signal`` (TP/SL only). Coercing
them to ENTRY market-buys double the position (Error #2 / XLU).

Usage::

    from duckclaw.signal_execution_bridge import (
        execute_signal_with_bracket,
        execute_protective_oca_for_signal,
        is_protective_signal_type,
    )

    result = await execute_signal_with_bracket(
        signal_id="sig_20260911_CEG_001",
        ticker="CEG",
        side="BUY",
        quantity=994,
        vault_db_path="/path/to/quant_traderdb1.duckdb",
    )

    # → {
    #     "status": "submitted",
    #     "main_order_id": 12345,
    #     "tp_order_id": 12346,
    #     "sl_order_id": 12347,
    #     "tp_price": 300.0,
    #     "sl_price": 245.0,
    # }

ponytail: Solo envía a IBKR si hay al menos un TP o SL configurado. Si ambos
son None, solo envía market order sin bracket — **except** protective types,
which refuse without ACTIVE TP/SL. Write commands van a la queue del vault
(db_path=vault_db_path), fire-and-forget — no espera confirmación de DB-Writer.
"""

from __future__ import annotations

import asyncio
import logging
import re
import math
from datetime import datetime, timezone
from typing import Optional

from duckclaw.trade_signals_ledger import fetch_trade_signal_row_from_path

_log = logging.getLogger(__name__)

# Protective / OCA types must never be coerced to ENTRY market buys.
PROTECTIVE_SIGNAL_TYPES = frozenset(
    {
        "BRACKET",
        "OCA",
        "PROTECTIVE",
        "PROTECT",
        "PROTECTIVE_OCA",
        "PROTECT_OCA",
        "TP_SL",
        "TPSL",
    }
)

_PROTECTIVE_KEYWORD_RE = re.compile(
    r"(BRACKET|PROTECTIVE_OCA|PROTECT_OCA|PROTECTIVE|\bOCA\b|TP[\s_/:-]?SL)",
    re.IGNORECASE,
)


def _connect_vault_ro(vault_db_path: str):
    """Read-only vault connection that waits out DB-Writer's lock (~5 s, see db_bridge).

    Several orders in one turn (e.g. trailing SL on 4 tickers) used to fail after the
    first: DB-Writer was still saving its rows and a single connect gave up at once.
    """
    from duckclaw.db_bridge import _duckdb_python_connect_with_retry

    return _duckdb_python_connect_with_retry(vault_db_path, read_only=True)


def is_protective_signal_type(signal_type: str | None) -> bool:
    """True when ``signal_type`` means place TP/SL only (no new market entry)."""
    st = str(signal_type or "").strip().upper().replace("-", "_")
    if not st:
        return False
    if st in PROTECTIVE_SIGNAL_TYPES:
        return True
    # Soft aliases: "BRACKET_OCA", "PROTECTIVE_BRACKET", etc.
    return bool(_PROTECTIVE_KEYWORD_RE.search(st))


def text_indicates_protective_order(text: str | None) -> bool:
    """Heuristic for tool-arg / rationale text that requests a protective OCA."""
    return bool(_PROTECTIVE_KEYWORD_RE.search(str(text or "")))


def refuse_protective_as_market_entry(signal_type: str | None) -> dict | None:
    """Return an error payload if ``signal_type`` must not go through market entry.

    Capadonna ``broker_execute_signal`` historically coerced unknown types
    (including ``BRACKET``) to ``ENTRY`` → market buy. Call this before sizing.
    """
    if not is_protective_signal_type(signal_type):
        return None
    st = str(signal_type or "").strip().upper() or "BRACKET"
    return {
        "status": "error",
        "error": "BLOCKED_PROTECTIVE_ORDER_ROUTE",
        "signal_type": st,
        "message": (
            f"signal_type={st} is a protective OCA (TP/SL only), not a market entry. "
            "Use execute_protective_oca_for_signal / submit_protective_oca_orders, "
            "or place the OCA from TWS. Do not coerce to ENTRY."
        ),
    }


def _is_protective_signal(strategy_name: str | None, rationale: str | None) -> bool:
    text = f"{strategy_name or ''} {rationale or ''}".lower()
    if "no es entrada nueva" in text or "no new entry" in text:
        return True
    return any(
        token in text
        for token in (
            "protective",
            "protectivo",
            "proteccion",
            "protección",
            "bracket oca",
            "oca bracket",
            "bracket protect",
            "tp/sl protection",
            "tp_sl_protection",
        )
    )


def _exit_side_for_position(position_side: str) -> str:
    return "SELL" if position_side == "BUY" else "BUY"


async def _live_position_qty(ib: object, ticker: str) -> float | None:
    sym = ticker.strip().upper()
    try:
        positions = ib.positions()  # type: ignore[attr-defined]
    except Exception:
        return None
    for pos in list(positions or []):
        contract = getattr(pos, "contract", None)
        if str(getattr(contract, "symbol", "") or "").strip().upper() == sym:
            try:
                return float(getattr(pos, "position"))
            except Exception:
                return None
    return None


def _finite_price(value: object) -> float | None:
    try:
        f = float(value)  # type: ignore[arg-type]
    except Exception:
        return None
    return f if math.isfinite(f) and f > 0 else None


async def _live_mark_price(ib: object, ticker: str) -> float | None:
    """Best-effort IBKR mark/last price. Caller decides whether missing is fatal.

    Tries realtime data first (type 1), then falls back to delayed (type 3) if
    nothing came back — some accounts have realtime entitlements for only a
    subset of symbols (this is exactly why CEG/SPY work but MU/MSFT/XLU don't:
    a per-symbol subscription gap, not a Gateway-wide outage). A delayed quote
    is fine here since ``mark`` only sanity-checks which side of price TP/SL
    sit on, not execution pricing.
    """
    try:
        from ib_insync import Stock
    except Exception:
        return None
    contract = Stock(ticker.strip().upper(), "SMART", "USD")
    try:
        qualify = getattr(ib, "qualifyContractsAsync", None)
        if callable(qualify):
            await qualify(contract)
    except Exception as exc:
        _log.warning("preflight qualifyContracts %s: %s", ticker, exc)

    set_market_data_type = getattr(ib, "reqMarketDataType", None)
    # ponytail: reqMarketDataType is connection-global, not per-request — fine for
    # this bridge's current sequential preflight-per-ticker usage; would need a
    # lock/serialize if this ever runs concurrent preflights on the same ib client.
    try:
        for data_type in (1, 3):  # 1=live, 3=delayed
            if callable(set_market_data_type):
                try:
                    set_market_data_type(data_type)
                except Exception as exc:
                    _log.warning(
                        "preflight reqMarketDataType(%s) %s: %s", data_type, ticker, exc
                    )
            ticker_obj = None
            try:
                ticker_obj = ib.reqMktData(contract, "", False, False)  # type: ignore[attr-defined]
                # ib.sleep() (sync, blocks via loop.run_until_complete) reenters the
                # already-running loop and raises "This event loop is already running"
                # when called from inside this coroutine — asyncio.sleep() is the
                # correct async-context equivalent (ib_insync keeps servicing the
                # socket in the background while this awaits, same as ib.sleep does).
                await asyncio.sleep(1.0)
                for attr in ("marketPrice", "last", "close", "bid", "ask"):
                    raw = getattr(ticker_obj, attr, None)
                    value = raw() if callable(raw) else raw
                    price = _finite_price(value)
                    if price is not None:
                        return price
            except Exception as exc:
                _log.warning("preflight mark type=%s failed %s: %s", data_type, ticker, exc)
            finally:
                try:
                    ib.cancelMktData(contract)  # type: ignore[attr-defined]
                except Exception:
                    pass
    finally:
        if callable(set_market_data_type):
            try:
                set_market_data_type(1)  # restore live default for other callers
            except Exception:
                pass
    return None


def _tp_sl_valid_for_mark(
    *,
    side: str,
    mark: float,
    tp_price: float | None,
    sl_price: float | None,
) -> bool:
    if tp_price is None and sl_price is None:
        return True
    if side == "BUY":
        if tp_price is not None and not (mark < tp_price):
            return False
        if sl_price is not None and not (sl_price < mark):
            return False
        return True
    if side == "SELL":
        if tp_price is not None and not (tp_price < mark):
            return False
        if sl_price is not None and not (mark < sl_price):
            return False
        return True
    return False


async def _open_orders_for_ticker(ib: object, ticker: str) -> list[object]:
    sym = ticker.strip().upper()
    try:
        # reqAllOpenOrders() (sync) blocks via loop.run_until_complete() and raises
        # "This event loop is already running" from inside this coroutine — use the
        # Async variant instead, same reason as the sleep() swap in _live_mark_price.
        req_all = getattr(ib, "reqAllOpenOrdersAsync", None)
        if callable(req_all):
            await req_all()
    except Exception as exc:
        _log.warning("preflight reqAllOpenOrders failed %s: %s", sym, exc)
    try:
        trades = list(ib.openTrades() or [])  # type: ignore[attr-defined]
    except Exception as exc:
        _log.warning("preflight openTrades failed %s: %s", sym, exc)
        return []
    out = []
    for trade in trades:
        contract = getattr(trade, "contract", None)
        if str(getattr(contract, "symbol", "") or "").strip().upper() == sym:
            out.append(trade)
    return out


def _daily_loss_limit_status(vault_db_path: str) -> dict:
    """Return optional daily loss guard status from quant_core tables.

    Supports both column-style and key/value-style ``trading_risk_constraints``.
    Missing table/columns means "not configured", not an execution error.
    """
    import duckdb

    try:
        con = _connect_vault_ro(vault_db_path)
    except Exception as exc:
        return {"ok": False, "error": f"PRE_FLIGHT_RISK_DB_UNAVAILABLE: {exc}"}
    try:
        rows = con.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'quant_core'
              AND table_name IN ('trading_risk_constraints', 'closed_trades')
            """
        ).fetchall()
        tables = {str(r[0]) for r in rows}
        if "trading_risk_constraints" not in tables:
            return {"ok": True, "configured": False}
        cols = {
            str(r[0])
            for r in con.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'quant_core'
                  AND table_name = 'trading_risk_constraints'
                """
            ).fetchall()
        }
        limit: float | None = None
        for col in ("daily_loss_limit", "max_daily_loss", "daily_loss_limit_usd"):
            if col in cols:
                row = con.execute(
                    f"""
                    SELECT {col}
                    FROM quant_core.trading_risk_constraints
                    WHERE {col} IS NOT NULL
                    LIMIT 1
                    """
                ).fetchone()
                limit = _finite_price(row[0]) if row else None
                if limit is not None:
                    break
        if limit is None and {"name", "value"}.issubset(cols):
            row = con.execute(
                """
                SELECT value
                FROM quant_core.trading_risk_constraints
                WHERE lower(cast(name AS VARCHAR)) IN (
                    'daily_loss_limit',
                    'max_daily_loss',
                    'daily_loss_limit_usd'
                )
                LIMIT 1
                """
            ).fetchone()
            limit = _finite_price(row[0]) if row else None
        if limit is None:
            return {"ok": True, "configured": False}
        if "closed_trades" not in tables:
            return {"ok": True, "configured": True, "limit": limit, "pnl": 0.0}
        today = datetime.now(timezone.utc).date().isoformat()
        row = con.execute(
            """
            SELECT coalesce(sum(pnl), 0)
            FROM quant_core.closed_trades
            WHERE cast(closed_at AS TIMESTAMP) >= cast(? AS TIMESTAMP)
            """,
            [today],
        ).fetchone()
        pnl = float(row[0] or 0.0) if row else 0.0
        return {
            "ok": pnl > -abs(limit),
            "configured": True,
            "limit": abs(limit),
            "pnl": pnl,
            "error": (
                f"PRE_FLIGHT_DAILY_LOSS_LIMIT: pnl_today={pnl:.2f} "
                f"limit={abs(limit):.2f}"
            ),
        }
    except Exception as exc:
        _log.warning("daily loss preflight unavailable: %s", exc)
        return {"ok": True, "configured": False, "warning": str(exc)}
    finally:
        con.close()


async def validate_execution_context(
    ib: object,
    *,
    signal_id: str,
    ticker: str,
    side: str,
    quantity: int,
    signal_type: str | None,
    vault_db_path: str,
    tp_price: float | None,
    sl_price: float | None,
    cancel_existing: bool = False,
) -> dict:
    """Fail-closed pre-flight for IBKR execution paths."""
    sym = ticker.strip().upper()
    side_u = side.strip().upper()
    st = (signal_type or "").strip().upper()
    base = {
        "signal_id": signal_id,
        "ticker": sym,
        "side": side_u,
        "quantity": quantity,
        "signal_type": st or None,
    }
    if quantity <= 0:
        return {**base, "ok": False, "error": "PRE_FLIGHT_BAD_QUANTITY"}

    risk = _daily_loss_limit_status(vault_db_path)
    if not risk.get("ok", True):
        return {**base, "ok": False, "error": risk.get("error", "PRE_FLIGHT_RISK_BLOCKED")}

    live_qty = await _live_position_qty(ib, sym)
    is_protective = is_protective_signal_type(st)
    is_exit = st == "EXIT"
    if is_protective or is_exit:
        if live_qty is None or abs(live_qty) <= 0:
            return {**base, "ok": False, "error": "PRE_FLIGHT_NO_LIVE_POSITION"}
        position_side = "BUY" if live_qty > 0 else "SELL"
        expected_side = position_side if is_protective else _exit_side_for_position(position_side)
        if side_u != expected_side:
            return {
                **base,
                "ok": False,
                "error": (
                    f"PRE_FLIGHT_SIDE_MISMATCH: position_side={position_side} "
                    f"requested={side_u}"
                ),
            }
        if quantity > int(abs(live_qty)):
            return {
                **base,
                "ok": False,
                "error": (
                    f"PRE_FLIGHT_QTY_EXCEEDS_POSITION: qty={quantity} "
                    f"live_qty={live_qty:g}"
                ),
            }

    open_orders = await _open_orders_for_ticker(ib, sym)
    if open_orders and not (is_protective and cancel_existing):
        ids = [
            str(getattr(getattr(t, "order", None), "orderId", "?"))
            for t in open_orders[:5]
        ]
        return {
            **base,
            "ok": False,
            "error": f"PRE_FLIGHT_OPEN_ORDERS_EXIST: ids={','.join(ids)}",
        }

    if tp_price is not None or sl_price is not None:
        mark = await _live_mark_price(ib, sym)
        if mark is None:
            return {**base, "ok": False, "error": "PRE_FLIGHT_MARK_UNAVAILABLE"}
        if not _tp_sl_valid_for_mark(
            side=side_u,
            mark=mark,
            tp_price=tp_price,
            sl_price=sl_price,
        ):
            return {
                **base,
                "ok": False,
                "error": (
                    f"PRE_FLIGHT_STALE_OR_INVALID_LEVELS: mark={mark:g} "
                    f"tp={tp_price} sl={sl_price}"
                ),
            }

    return {
        **base,
        "ok": True,
        "live_qty": live_qty,
        "open_orders": len(open_orders),
        "risk": risk,
    }


# ---------------------------------------------------------------------------
# Signal Execution
# ---------------------------------------------------------------------------


def _read_active_tp_sl(vault_db_path: str, ticker: str) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """Return (tp, sl, error). error is set when the read itself fails."""
    import duckdb

    try:
        con = _connect_vault_ro(vault_db_path)
        try:
            tp_sl = con.execute(
                """
                SELECT take_profit, stop_loss
                FROM quant_core.tp_sl_levels
                WHERE ticker = ? AND status = 'ACTIVE'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                [ticker],
            ).fetchone()
        finally:
            con.close()
    except Exception as exc:
        return None, None, f"Error leyendo TP/SL levels: {exc}"

    tp_price = float(tp_sl[0]) if tp_sl and tp_sl[0] is not None else None
    sl_price = float(tp_sl[1]) if tp_sl and tp_sl[1] is not None else None
    return tp_price, sl_price, None


async def execute_protective_oca_for_signal(
    signal_id: str,
    ticker: str,
    position_side: str,
    quantity: int,
    vault_db_path: str,
    host: str | None = None,
    port: int | None = None,
    client_id: int | None = None,
    *,
    cancel_existing: bool = True,
) -> dict:
    """Place TP/SL GTC OCA for an **existing** position — no market entry.

    Use for ``signal_type`` in :data:`PROTECTIVE_SIGNAL_TYPES` (BRACKET, OCA, …).
    """
    from duckclaw.db_write_queue import enqueue_typed_command
    from duckclaw.ibkr_bracket_orders import connect_ibkr, submit_protective_oca_orders
    from duckclaw.write_commands import (
        InsertIbkrOrderCommand,
        UpdateTradeSignalExecutedCommand,
    )

    timestamp = datetime.now(timezone.utc)
    side = (position_side or "").strip().upper()
    base = {
        "signal_id": signal_id,
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "main_order_id": None,
        "tp_order_id": None,
        "sl_order_id": None,
        "tp_price": None,
        "sl_price": None,
        "timestamp": timestamp,
        "route": "protective_oca",
    }

    if side not in ("BUY", "SELL"):
        return {**base, "status": "error", "error": f"position_side debe ser BUY|SELL, got: {position_side}"}
    if quantity <= 0:
        return {**base, "status": "error", "error": f"quantity debe ser > 0, got: {quantity}"}

    tp_price, sl_price, read_err = _read_active_tp_sl(vault_db_path, ticker)
    base["tp_price"] = tp_price
    base["sl_price"] = sl_price
    if read_err:
        return {**base, "status": "error", "error": read_err}
    if tp_price is None and sl_price is None:
        return {
            **base,
            "status": "error",
            "error": (
                f"No ACTIVE tp_sl_levels for {ticker}; refuse protective OCA "
                "(would otherwise fall through to a naked market order)."
            ),
        }

    try:
        ib = await connect_ibkr(host=host, port=port, client_id=client_id)
    except Exception as exc:
        return {**base, "status": "error", "error": f"Error conectando a IBKR: {exc}"}

    try:
        preflight = await validate_execution_context(
            ib,
            signal_id=signal_id,
            ticker=ticker,
            side=side,
            quantity=quantity,
            signal_type="BRACKET",
            vault_db_path=vault_db_path,
            tp_price=tp_price,
            sl_price=sl_price,
            cancel_existing=cancel_existing,
        )
        if not preflight.get("ok"):
            try:
                ib.disconnect()
            except Exception:
                pass
            return {**base, "status": "error", "error": preflight.get("error")}
        result = await submit_protective_oca_orders(
            ib,
            ticker,
            side,
            quantity,
            tp_price,
            sl_price,
            cancel_existing=cancel_existing,
        )
        ib.disconnect()
    except Exception as exc:
        try:
            ib.disconnect()
        except Exception:
            pass
        return {**base, "status": "error", "error": f"Error enviando protective OCA: {exc}"}

    close_action = "SELL" if side == "BUY" else "BUY"
    oca_group = result.get("oca_group")
    if result.get("tp_order_id"):
        enqueue_typed_command(
            InsertIbkrOrderCommand(
                order_id=result["tp_order_id"],
                ticker=ticker,
                side=close_action,
                quantity=quantity,
                order_type="LIMIT",
                limit_price=tp_price,
                status="submitted",
                submitted_at=timestamp.isoformat(),
                trade_signal_id=signal_id,
                notes=f"protective_oca_tp:{oca_group}",
            ),
            db_path=vault_db_path,
        )
    if result.get("sl_order_id"):
        enqueue_typed_command(
            InsertIbkrOrderCommand(
                order_id=result["sl_order_id"],
                ticker=ticker,
                side=close_action,
                quantity=quantity,
                order_type="STOP",
                stop_price=sl_price,
                status="submitted",
                submitted_at=timestamp.isoformat(),
                trade_signal_id=signal_id,
                notes=f"protective_oca_sl:{oca_group}",
            ),
            db_path=vault_db_path,
        )
    enqueue_typed_command(
        UpdateTradeSignalExecutedCommand(
            signal_id=signal_id,
            executed_at=timestamp.isoformat(),
        ),
        db_path=vault_db_path,
    )

    _log.info(
        "Protective OCA for signal %s: %s qty=%s tp=%s sl=%s",
        signal_id,
        ticker,
        quantity,
        result.get("tp_order_id"),
        result.get("sl_order_id"),
    )
    return {
        **base,
        "status": "submitted",
        "tp_order_id": result.get("tp_order_id"),
        "sl_order_id": result.get("sl_order_id"),
        "sl_order_type": result.get("sl_order_type"),
        "sl_fallback_reason": result.get("sl_fallback_reason"),
        "oca_group": oca_group,
    }


async def execute_signal_with_bracket(
    signal_id: str,
    ticker: str,
    side: str,
    quantity: int,
    vault_db_path: str,
    host: str | None = None,
    port: int | None = None,
    client_id: int | None = None,
    *,
    signal_type: str | None = None,
) -> dict:
    """Ejecuta señal de trading con bracket order (TP/SL) en IBKR.

    Workflow:
        1. Si ``signal_type`` es protectivo (BRACKET/OCA/…), desvía a
           :func:`execute_protective_oca_for_signal` (sin market entry).
        2. Lee tp_sl_levels para el ticker (ACTIVE)
        3. Conecta a IBKR Gateway/TWS
        4. Envía bracket order (main + TP + SL)
        5. Registra en quant_core.ibkr_orders (via write queue)
        6. Actualiza trade_signals.executed_at

    Args:
        signal_id: ID de la señal en trade_signals
        ticker: Símbolo del instrumento (ej: "CEG")
        side: "BUY" o "SELL" (entry side, or open position side for protective)
        quantity: Cantidad de shares/contratos
        vault_db_path: Path al DuckDB vault (lectura de TP/SL levels)
        host: IBKR Gateway host (default: IBKR_HOST env var)
        port: IBKR Gateway port (default: IBKR_PORT env var)
        client_id: Client ID (default: IBKR_CLIENT_ID env var)
        signal_type: Optional ledger type. ``BRACKET``/OCA/PROTECTIVE never
            market-enter — they place protective OCA only.

    Returns:
        {
            "status": "submitted" | "error",
            "signal_id": str,
            "ticker": str,
            "side": str,
            "quantity": int,
            "main_order_id": int,
            "tp_order_id": Optional[int],
            "sl_order_id": Optional[int],
            "tp_price": Optional[float],
            "sl_price": Optional[float],
            "timestamp": datetime,
            "error": Optional[str],
        }

    Raises:
        ImportError: Si ib_insync no está instalado
        ConnectionError: Si no puede conectar a IBKR
        RuntimeError: Si error al enviar órdenes

    Example:
        >>> result = await execute_signal_with_bracket(
        ...     signal_id="sig_20260911_CEG_001",
        ...     ticker="CEG",
        ...     side="BUY",
        ...     quantity=994,
        ...     vault_db_path="/path/to/quant_traderdb1.duckdb",
        ... )
        >>> result["status"]
        'submitted'
        >>> result["main_order_id"]
        12345
    """
    from duckclaw.db_write_queue import enqueue_typed_command
    from duckclaw.ibkr_bracket_orders import (
        connect_ibkr,
        submit_bracket_order,
        submit_protective_oca_orders,
    )
    from duckclaw.write_commands import (
        InsertIbkrOrderCommand,
        UpdateTradeSignalExecutedCommand,
    )

    timestamp = datetime.now(timezone.utc)

    # Protective types must never place a market entry (Error #2: BRACKET→buy).
    if is_protective_signal_type(signal_type):
        _log.info(
            "Routing signal_id=%s signal_type=%s → protective OCA (no market entry)",
            signal_id,
            signal_type,
        )
        return await execute_protective_oca_for_signal(
            signal_id=signal_id,
            ticker=ticker,
            position_side=side,
            quantity=quantity,
            vault_db_path=vault_db_path,
            host=host,
            port=port,
            client_id=client_id,
        )

    # 1. Leer niveles TP/SL del vault
    _log.info(f"Leyendo TP/SL levels para {ticker} (signal_id={signal_id})")

    tp_price, sl_price, read_err = _read_active_tp_sl(vault_db_path, ticker)
    if read_err:
        _log.error("%s", read_err)
        return {
            "status": "error",
            "signal_id": signal_id,
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "main_order_id": None,
            "tp_order_id": None,
            "sl_order_id": None,
            "tp_price": None,
            "sl_price": None,
            "timestamp": timestamp,
            "error": read_err,
        }

    try:
        signal_row = fetch_trade_signal_row_from_path(vault_db_path, signal_id)
    except Exception as exc:
        _log.error("Error leyendo trade_signals: %s", exc)
        signal_row = None

    signal_action = str((signal_row or {}).get("action") or "")
    strategy_name = str((signal_row or {}).get("strategy_name") or "")
    rationale = str((signal_row or {}).get("rationale") or "")
    raw_qty = (signal_row or {}).get("order_qty")
    signal_order_qty = (
        int(abs(float(raw_qty)))
        if raw_qty is not None and float(raw_qty) != 0
        else None
    )
    ledger_st = str((signal_row or {}).get("signal_type") or "").strip() or None
    # Ledger protective type wins over a missing/stale caller signal_type.
    if is_protective_signal_type(ledger_st):
        _log.info(
            "Routing signal_id=%s signal_type=%s (from ledger) → protective OCA",
            signal_id,
            ledger_st,
        )
        return await execute_protective_oca_for_signal(
            signal_id=signal_id,
            ticker=ticker,
            position_side=side,
            quantity=quantity,
            vault_db_path=vault_db_path,
            host=host,
            port=port,
            client_id=client_id,
        )
    if not signal_type and ledger_st:
        signal_type = ledger_st
    protective_only = _is_protective_signal(strategy_name, rationale)

    _log.info(
        f"Niveles TP/SL para {ticker}: TP={tp_price}, SL={sl_price} "
        f"(None = no configurado)"
    )

    if tp_price is None and sl_price is None:
        msg = "Refusing to submit IBKR market order without TP/SL levels"
        _log.error("%s: signal_id=%s ticker=%s", msg, signal_id, ticker)
        return {
            "status": "error",
            "signal_id": signal_id,
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "main_order_id": None,
            "tp_order_id": None,
            "sl_order_id": None,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "timestamp": timestamp,
            "error": msg,
        }

    # 2. Conectar a IBKR
    try:
        ib = await connect_ibkr(host=host, port=port, client_id=client_id)
    except Exception as exc:
        _log.error(f"Error conectando a IBKR: {exc}")
        return {
            "status": "error",
            "signal_id": signal_id,
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "main_order_id": None,
            "tp_order_id": None,
            "sl_order_id": None,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "timestamp": timestamp,
            "error": f"Error conectando a IBKR: {exc}",
        }

    # 3. Enviar bracket/protective order
    try:
        if protective_only:
            live_qty = await _live_position_qty(ib, ticker)
            protective_qty = int(abs(live_qty)) if live_qty and abs(live_qty) > 0 else (
                signal_order_qty or int(quantity)
            )
            position_side = "SELL" if live_qty is not None and live_qty < 0 else (
                signal_action.strip().upper() or side
            )
            if protective_qty <= 0:
                raise ValueError("protective OCA requires existing positive quantity")
            preflight = await validate_execution_context(
                ib,
                signal_id=signal_id,
                ticker=ticker,
                side=position_side,
                quantity=protective_qty,
                signal_type="BRACKET",
                vault_db_path=vault_db_path,
                tp_price=tp_price,
                sl_price=sl_price,
                cancel_existing=True,
            )
            if not preflight.get("ok"):
                raise ValueError(str(preflight.get("error") or "PRE_FLIGHT_BLOCKED"))
            result = await submit_protective_oca_orders(
                ib,
                ticker,
                position_side,
                protective_qty,
                tp_price=tp_price,
                sl_price=sl_price,
                cancel_existing=True,
            )
            quantity = protective_qty
            side = position_side
        else:
            preflight = await validate_execution_context(
                ib,
                signal_id=signal_id,
                ticker=ticker,
                side=side,
                quantity=quantity,
                signal_type=signal_type,
                vault_db_path=vault_db_path,
                tp_price=tp_price,
                sl_price=sl_price,
            )
            if not preflight.get("ok"):
                raise ValueError(str(preflight.get("error") or "PRE_FLIGHT_BLOCKED"))
            result = await submit_bracket_order(
                ib, ticker, side, quantity, tp_price, sl_price
            )
        ib.disconnect()
    except Exception as exc:
        _log.error(f"Error enviando bracket order: {exc}")
        try:
            ib.disconnect()
        except Exception:
            pass
        return {
            "status": "error",
            "signal_id": signal_id,
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "main_order_id": None,
            "tp_order_id": None,
            "sl_order_id": None,
            "tp_price": tp_price,
            "sl_price": sl_price,
            "timestamp": timestamp,
            "error": f"Error enviando bracket order: {exc}",
        }

    # 4. Registrar órdenes en quant_core.ibkr_orders (via write queue)
    _log.info(
        f"Registrando órdenes en ibkr_orders: "
        f"main={result['main_order_id']}, tp={result['tp_order_id']}, sl={result['sl_order_id']}"
    )

    # Main order (protective OCA has no entry/main order)
    if result["main_order_id"]:
        main_cmd = InsertIbkrOrderCommand(
            order_id=result["main_order_id"],
            ticker=ticker,
            side=side,
            quantity=quantity,
            order_type="MARKET",
            status="submitted",
            submitted_at=timestamp.isoformat(),
            trade_signal_id=signal_id,
        )
        enqueue_typed_command(main_cmd, db_path=vault_db_path)

    # TP order
    if result["tp_order_id"]:
        close_action = "SELL" if side == "BUY" else "BUY"
        tp_cmd = InsertIbkrOrderCommand(
            order_id=result["tp_order_id"],
            ticker=ticker,
            side=close_action,
            quantity=quantity,
            order_type="LIMIT",
            limit_price=tp_price,
            parent_order_id=result["main_order_id"],
            status="submitted",
            submitted_at=timestamp.isoformat(),
            trade_signal_id=signal_id,
            notes="Take Profit (GTC)" if result["main_order_id"] else f"Protective OCA TP {result.get('oca_group')}",
        )
        enqueue_typed_command(tp_cmd, db_path=vault_db_path)

    # SL order
    if result["sl_order_id"]:
        close_action = "SELL" if side == "BUY" else "BUY"
        sl_cmd = InsertIbkrOrderCommand(
            order_id=result["sl_order_id"],
            ticker=ticker,
            side=close_action,
            quantity=quantity,
            order_type="STOP",
            stop_price=sl_price,
            parent_order_id=result["main_order_id"],
            status="submitted",
            submitted_at=timestamp.isoformat(),
            trade_signal_id=signal_id,
            notes="Stop Loss (GTC)" if result["main_order_id"] else f"Protective OCA SL {result.get('oca_group')}",
        )
        enqueue_typed_command(sl_cmd, db_path=vault_db_path)

    # 5. Actualizar trade_signals.executed_at
    exec_cmd = UpdateTradeSignalExecutedCommand(
        signal_id=signal_id,
        executed_at=timestamp.isoformat(),
    )
    enqueue_typed_command(exec_cmd, db_path=vault_db_path)

    _log.info(
        f"✅ Signal {signal_id} ejecutado: {side} {quantity} {ticker} "
        f"— main={result['main_order_id']}, tp={result['tp_order_id']}, sl={result['sl_order_id']}"
    )

    return {
        "status": "submitted",
        "signal_id": signal_id,
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "main_order_id": result["main_order_id"],
        "tp_order_id": result["tp_order_id"],
        "sl_order_id": result["sl_order_id"],
        "tp_price": tp_price,
        "sl_price": sl_price,
        "timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# Batch Execution (múltiples señales)
# ---------------------------------------------------------------------------


async def execute_signals_batch(
    signal_specs: list[dict],
    vault_db_path: str,
    host: str | None = None,
    port: int | None = None,
    client_id: int | None = None,
) -> list[dict]:
    """Ejecuta múltiples señales en batch.

    Args:
        signal_specs: Lista de dicts con keys: signal_id, ticker, side, quantity
        vault_db_path: Path al DuckDB vault
        host: IBKR Gateway host (optional)
        port: IBKR Gateway port (optional)
        client_id: Client ID (optional)

    Returns:
        Lista de resultados (mismo formato que execute_signal_with_bracket)

    Example:
        >>> specs = [
        ...     {"signal_id": "sig_1", "ticker": "CEG", "side": "BUY", "quantity": 994},
        ...     {"signal_id": "sig_2", "ticker": "SPY", "side": "SELL", "quantity": 100},
        ... ]
        >>> results = await execute_signals_batch(specs, vault_db_path)
        >>> len(results)
        2
    """
    results = []

    for spec in signal_specs:
        try:
            result = await execute_signal_with_bracket(
                signal_id=spec["signal_id"],
                ticker=spec["ticker"],
                side=spec["side"],
                quantity=spec["quantity"],
                vault_db_path=vault_db_path,
                host=host,
                port=port,
                client_id=client_id,
                signal_type=spec.get("signal_type"),
            )
            results.append(result)
        except Exception as exc:
            _log.error(
                f"Error ejecutando signal {spec['signal_id']}: {exc}"
            )
            results.append(
                {
                    "status": "error",
                    "signal_id": spec["signal_id"],
                    "ticker": spec["ticker"],
                    "side": spec["side"],
                    "quantity": spec["quantity"],
                    "main_order_id": None,
                    "tp_order_id": None,
                    "sl_order_id": None,
                    "tp_price": None,
                    "sl_price": None,
                    "timestamp": datetime.now(timezone.utc),
                    "error": str(exc),
                }
            )

    return results
