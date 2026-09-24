"""IBKR bracket orders skill — ejecuta señales con TP/SL automático."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from langchain_core.tools import StructuredTool

_log = logging.getLogger(__name__)


def register_ibkr_bracket_orders_skill(
    tools_list: list[Any],
    ibkr_bracket_orders_config: Optional[dict] = None,
    vault_db_path: Optional[str] = None,
) -> None:
    """Register IBKR bracket order execution tool.
    
    Args:
        tools_list: List to append tools to
        ibkr_bracket_orders_config: Config dict (enabled check)
        vault_db_path: Path to DuckDB vault (for tp_sl_levels)
    """
    cfg = ibkr_bracket_orders_config if isinstance(ibkr_bracket_orders_config, dict) else {}
    if cfg.get("enabled") is False:
        return

    if not vault_db_path:
        _log.warning(
            "ibkr_bracket_orders skill requires vault_db_path — "
            "tool not registered (tp_sl_levels inaccessible)"
        )
        return

    # Import async bridge — defer to avoid import errors if ib_insync not installed
    try:
        from duckclaw.signal_execution_bridge import execute_signal_with_bracket
    except ImportError as exc:
        _log.warning(
            f"ibkr_bracket_orders skill import failed: {exc} — "
            "install with: uv sync --extra trading"
        )
        return

    def _execute_signal_bracket_sync(
        signal_id: str,
        ticker: str,
        side: str,
        quantity: int,
        signal_type: str = "ENTRY",
    ) -> str:
        """Ejecuta señal de trading con bracket order (TP/SL automático en IBKR).
        
        Lee niveles TP/SL de tp_sl_levels (ACTIVE), envía bracket order a IBKR
        (main + TP + SL como órdenes GTC), registra en ibkr_orders, y actualiza
        trade_signals.executed_at.

        Si ``signal_type`` es BRACKET/OCA/PROTECTIVE, **no** abre mercado: solo
        coloca OCA protectiva sobre la posición existente (``side`` = lado abierto).
        
        Args:
            signal_id: ID de la señal en trade_signals
            ticker: Símbolo del instrumento (ej: "CEG", "SPY")
            side: "BUY" o "SELL"
            quantity: Cantidad de shares/contratos (entero > 0)
            signal_type: ENTRY (default) | EXIT | BRACKET | OCA | PROTECTIVE
        
        Returns:
            JSON con order_ids, status, TP/SL prices, o error details
        
        Example output:
            {
                "status": "submitted",
                "signal_id": "sig_20260911_CEG_001",
                "ticker": "CEG",
                "side": "BUY",
                "quantity": 994,
                "main_order_id": 12345,
                "tp_order_id": 12346,
                "sl_order_id": 12347,
                "tp_price": 300.0,
                "sl_price": 245.0,
                "timestamp": "2026-09-11T06:00:00+00:00"
            }
        """
        import asyncio

        # ponytail: sync wrapper for async tool — LangChain graph is sync
        # AsyncIO event loop handling depends on whether we're already in async context
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — create new one (standalone execution)
            loop = None

        coro = execute_signal_with_bracket(
            signal_id=signal_id,
            ticker=ticker,
            side=side,
            quantity=quantity,
            vault_db_path=vault_db_path,
            signal_type=signal_type,
        )
        if loop and loop.is_running():
            # Already in async context (e.g. gateway handler) — use run_in_executor
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                result = future.result(timeout=30)
        else:
            # No async context — run directly
            result = asyncio.run(coro)

        return json.dumps(result, ensure_ascii=False, default=str)

    tools_list.append(
        StructuredTool.from_function(
            _execute_signal_bracket_sync,
            name="execute_signal_with_bracket",
            description=(
                "[IBKR Trading] Ejecuta señal de trading enviando bracket order (main + TP + SL) "
                "a Interactive Brokers. Las órdenes TP/SL son GTC (Good Till Canceled) y se ejecutan "
                "automáticamente cuando el precio alcanza los niveles configurados. "
                "\n\n"
                "Cuándo usar: Después de HITL approval de una señal BUY/SELL que tenga niveles "
                "TP/SL configurados en tp_sl_levels (status=ACTIVE). NO usar para señales sin TP/SL "
                "o antes de approval. "
                "\n\n"
                "signal_type=BRACKET|OCA|PROTECTIVE: solo TP/SL protectivo (sin market buy). "
                "Nunca uses execute_approved_signal para BRACKET — el hook de broker lo trata como ENTRY. "
                "\n\n"
                "Args: signal_id (str), ticker (str), side ('BUY'|'SELL'), quantity (int > 0), "
                "signal_type (str, default ENTRY). "
                "\n\n"
                "Returns: JSON con order_ids (main, tp, sl), prices, status='submitted' o status='error'. "
                "Copia el JSON completo en tu reporte. Si status='error', revisar campo 'error' y "
                "troubleshoot (Gateway no conectado, TP/SL no configurados, etc)."
            ),
        )
    )

    _log.info(
        "IBKR bracket orders skill registrado — execute_signal_with_bracket disponible"
    )
