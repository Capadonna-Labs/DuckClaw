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

import logging
import re
from datetime import datetime, timezone
from typing import Optional

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


# ---------------------------------------------------------------------------
# Signal Execution
# ---------------------------------------------------------------------------


def _read_active_tp_sl(vault_db_path: str, ticker: str) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """Return (tp, sl, error). error is set when the read itself fails."""
    import duckdb

    try:
        con = duckdb.connect(vault_db_path, read_only=True)
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
        result = await submit_protective_oca_orders(
            ib,
            ticker,
            side,
            quantity,
            tp_price,
            sl_price,
            cancel_existing=cancel_existing,
        )
        await ib.disconnect()
    except Exception as exc:
        try:
            await ib.disconnect()
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
    from duckclaw.ibkr_bracket_orders import connect_ibkr, submit_bracket_order
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

    _log.info(
        f"Niveles TP/SL para {ticker}: TP={tp_price}, SL={sl_price} "
        f"(None = no configurado)"
    )

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

    # 3. Enviar bracket order
    try:
        result = await submit_bracket_order(
            ib, ticker, side, quantity, tp_price, sl_price
        )
        await ib.disconnect()
    except Exception as exc:
        _log.error(f"Error enviando bracket order: {exc}")
        try:
            await ib.disconnect()
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

    # Main order
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
            notes="Take Profit (GTC)",
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
            notes="Stop Loss (GTC)",
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
