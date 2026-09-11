"""Signal Execution Bridge — link trade signals → IBKR bracket orders.

Conecta las señales de trading (`trade_signals`, `tp_sl_levels`) con la ejecución
automática de bracket orders en IBKR. Lee los niveles TP/SL configurados y los
envía como órdenes GTC al broker.

Architecture:
    1. Read signal from trade_signals table
    2. Fetch TP/SL levels from tp_sl_levels (ACTIVE)
    3. Create bracket order (main + TP + SL)
    4. Submit to IBKR Gateway/TWS
    5. Record order_ids in quant_core.ibkr_orders
    6. Update trade_signals.executed_at

Usage::

    from duckclaw.signal_execution_bridge import execute_signal_with_bracket

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
son None, solo envía market order sin bracket. Write commands van a la queue
(fire-and-forget) — no espera confirmación de DB-Writer.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Signal Execution
# ---------------------------------------------------------------------------


async def execute_signal_with_bracket(
    signal_id: str,
    ticker: str,
    side: str,
    quantity: int,
    vault_db_path: str,
    host: str | None = None,
    port: int | None = None,
    client_id: int | None = None,
) -> dict:
    """Ejecuta señal de trading con bracket order (TP/SL) en IBKR.

    Workflow:
        1. Lee tp_sl_levels para el ticker (ACTIVE)
        2. Conecta a IBKR Gateway/TWS
        3. Envía bracket order (main + TP + SL)
        4. Registra en quant_core.ibkr_orders (via write queue)
        5. Actualiza trade_signals.executed_at

    Args:
        signal_id: ID de la señal en trade_signals
        ticker: Símbolo del instrumento (ej: "CEG")
        side: "BUY" o "SELL"
        quantity: Cantidad de shares/contratos
        vault_db_path: Path al DuckDB vault (lectura de TP/SL levels)
        host: IBKR Gateway host (default: IBKR_HOST env var)
        port: IBKR Gateway port (default: IBKR_PORT env var)
        client_id: Client ID (default: IBKR_CLIENT_ID env var)

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
    import duckdb

    from duckclaw.db_write_queue import enqueue_write_command
    from duckclaw.ibkr_bracket_orders import connect_ibkr, submit_bracket_order

    timestamp = datetime.now(timezone.utc)

    # 1. Leer niveles TP/SL del vault
    _log.info(f"Leyendo TP/SL levels para {ticker} (signal_id={signal_id})")

    try:
        con = duckdb.connect(vault_db_path, read_only=True)
        tp_sl = con.execute(
            """
            SELECT tp, sl
            FROM quant_core.tp_sl_levels
            WHERE ticker = ? AND status = 'ACTIVE'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            [ticker],
        ).fetchone()
        con.close()
    except Exception as exc:
        _log.error(f"Error leyendo tp_sl_levels: {exc}")
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
            "error": f"Error leyendo TP/SL levels: {exc}",
        }

    tp_price = tp_sl[0] if tp_sl else None
    sl_price = tp_sl[1] if tp_sl else None

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
    enqueue_write_command(
        "insert_ibkr_order",
        {
            "order_id": result["main_order_id"],
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "order_type": "MARKET",
            "status": "submitted",
            "submitted_at": timestamp.isoformat(),
            "trade_signal_id": signal_id,
        },
    )

    # TP order
    if result["tp_order_id"]:
        close_action = "SELL" if side == "BUY" else "BUY"
        enqueue_write_command(
            "insert_ibkr_order",
            {
                "order_id": result["tp_order_id"],
                "ticker": ticker,
                "side": close_action,
                "quantity": quantity,
                "order_type": "LIMIT",
                "limit_price": tp_price,
                "parent_order_id": result["main_order_id"],
                "status": "submitted",
                "submitted_at": timestamp.isoformat(),
                "trade_signal_id": signal_id,
                "notes": "Take Profit (GTC)",
            },
        )

    # SL order
    if result["sl_order_id"]:
        close_action = "SELL" if side == "BUY" else "BUY"
        enqueue_write_command(
            "insert_ibkr_order",
            {
                "order_id": result["sl_order_id"],
                "ticker": ticker,
                "side": close_action,
                "quantity": quantity,
                "order_type": "STOP",
                "stop_price": sl_price,
                "parent_order_id": result["main_order_id"],
                "status": "submitted",
                "submitted_at": timestamp.isoformat(),
                "trade_signal_id": signal_id,
                "notes": "Stop Loss (GTC)",
            },
        )

    # 5. Actualizar trade_signals.executed_at
    enqueue_write_command(
        "update_trade_signal_executed",
        {
            "signal_id": signal_id,
            "executed_at": timestamp.isoformat(),
        },
    )

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
