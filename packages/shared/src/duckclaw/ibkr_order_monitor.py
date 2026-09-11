"""IBKR Order Monitor — sincroniza estado de órdenes desde el broker.

Consulta periódicamente el estado de órdenes activas en IBKR y actualiza
la tabla `quant_core.ibkr_orders` con fills, cancelaciones, y status changes.

Architecture:
    - Cron job (cada 1 minuto recomendado)
    - Lee órdenes pending de `ibkr_orders` (status = 'submitted', 'partial')
    - Consulta estado desde IBKR via ib_insync
    - Actualiza status, filled_qty, filled_price via write queue

Usage::

    # Como script standalone (cron job)
    python -m duckclaw.ibkr_order_monitor --vault-db /path/to/vault.duckdb

    # O programáticamente
    from duckclaw.ibkr_order_monitor import sync_order_status

    await sync_order_status(vault_db_path="/path/to/vault.duckdb")

Cron Setup::

    # Correr cada minuto
    * * * * * cd /root/duckclaw && uv run python -m duckclaw.ibkr_order_monitor \\
        --vault-db /path/to/quant_traderdb1.duckdb \\
        >> /var/log/ibkr_order_monitor.log 2>&1

PM2 Setup::

    pm2 start python --name "IBKR-Order-Monitor" -- \\
        -m duckclaw.ibkr_order_monitor \\
        --vault-db /path/to/quant_traderdb1.duckdb \\
        --interval 60

ponytail: Solo consulta órdenes pending (no escala a miles de órdenes históricas).
Timeout de 10s por orden — si IBKR no responde, skip y log warning. Write commands
fire-and-forget — no espera confirmación del DB-Writer.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Order Status Sync
# ---------------------------------------------------------------------------


async def sync_order_status(
    vault_db_path: str,
    host: str | None = None,
    port: int | None = None,
    client_id: int | None = None,
) -> dict:
    """Sincroniza estado de órdenes activas desde IBKR.

    Args:
        vault_db_path: Path al DuckDB vault (lectura de órdenes pending)
        host: IBKR Gateway host (default: IBKR_HOST env var)
        port: IBKR Gateway port (default: IBKR_PORT env var)
        client_id: Client ID (default: IBKR_MONITOR_CLIENT_ID, else IBKR_CLIENT_ID+1, else 2)

    Returns:
        {
            "pending_orders": int,
            "synced": int,
            "errors": int,
            "updates": [
                {"order_id": int, "status": str, "filled_qty": float, ...},
                ...
            ],
        }

    Example:
        >>> result = await sync_order_status("/path/to/vault.duckdb")
        >>> result["synced"]
        3
    """
    import duckdb

    from duckclaw.db_write_queue import enqueue_typed_command
    from duckclaw.ibkr_bracket_orders import connect_ibkr
    from duckclaw.write_commands import UpdateIbkrOrderStatusCommand

    _log.info(f"Iniciando sincronización de órdenes: {vault_db_path}")

    # 1. Leer órdenes pending del vault
    try:
        con = duckdb.connect(vault_db_path, read_only=True)
        pending = con.execute(
            """
            SELECT order_id, ticker, side, quantity, order_type
            FROM quant_core.ibkr_orders
            WHERE status IN ('submitted', 'partial')
            ORDER BY submitted_at DESC
            """
        ).fetchall()
        con.close()
    except Exception as exc:
        _log.error(f"Error leyendo órdenes pending: {exc}")
        return {
            "pending_orders": 0,
            "synced": 0,
            "errors": 1,
            "updates": [],
            "error": str(exc),
        }

    if not pending:
        _log.info("No hay órdenes pending para sincronizar")
        return {
            "pending_orders": 0,
            "synced": 0,
            "errors": 0,
            "updates": [],
        }

    _log.info(f"Encontradas {len(pending)} órdenes pending")

    # 2. Conectar a IBKR
    # Client ID distinto del execution path para evitar colisión de sesión IBKR
    if client_id is None:
        import os

        monitor_raw = os.getenv("IBKR_MONITOR_CLIENT_ID")
        if monitor_raw:
            client_id = int(monitor_raw)
        else:
            base = int(os.getenv("IBKR_CLIENT_ID", "1"))
            client_id = base + 1

    try:
        ib = await connect_ibkr(host=host, port=port, client_id=client_id)
    except Exception as exc:
        _log.error(f"Error conectando a IBKR: {exc}")
        return {
            "pending_orders": len(pending),
            "synced": 0,
            "errors": 1,
            "updates": [],
            "error": f"Error conectando a IBKR: {exc}",
        }

    # 3. Consultar estado de cada orden
    updates = []
    synced = 0
    errors = 0

    # Map de status IBKR → status DB
    status_map = {
        "Filled": "filled",
        "Cancelled": "cancelled",
        "PendingSubmit": "submitted",
        "PreSubmitted": "submitted",
        "Submitted": "submitted",
        "Inactive": "inactive",
        # PartialFilled no es status IBKR real — se deriva abajo

    }

    for order_id, ticker, side, quantity, order_type in pending:
        try:
            # Consultar estado en IBKR
            trades = ib.trades()
            trade = next((t for t in trades if t.order.orderId == order_id), None)

            if not trade:
                _log.warning(f"Orden {order_id} ({ticker}) no encontrada en IBKR — skip")
                continue

            order_status = trade.orderStatus.status
            filled_qty = trade.orderStatus.filled
            filled_price = trade.orderStatus.avgFillPrice
            remaining = trade.orderStatus.remaining

            db_status = status_map.get(order_status, "unknown")
            # IBKR no emite "PartialFilled": parcial = Submitted/PreSubmitted con fill incompleto
            if db_status == "submitted" and float(filled_qty or 0) > 0 and float(remaining or 0) > 0:
                db_status = "partial"

            _log.info(
                f"Orden {order_id} ({ticker}): {order_status} → {db_status}, "
                f"filled={filled_qty}/{quantity}, price={filled_price:.2f}"
            )

            # Actualizar en DB via write queue
            update_cmd = UpdateIbkrOrderStatusCommand(
                order_id=order_id,
                status=db_status,
                filled_qty=int(filled_qty or 0),
                filled_price=filled_price if filled_price > 0 else None,
                filled_at=datetime.now(timezone.utc).isoformat() if db_status == "filled" else "",
                cancelled_at=datetime.now(timezone.utc).isoformat() if db_status == "cancelled" else "",
            )
            enqueue_typed_command(update_cmd, db_path=vault_db_path)

            updates.append(
                {
                    "order_id": order_id,
                    "ticker": ticker,
                    "status": db_status,
                    "filled_qty": filled_qty,
                    "filled_price": filled_price if filled_price > 0 else None,
                    "remaining": remaining,
                }
            )
            synced += 1

        except Exception as exc:
            _log.error(f"Error sincronizando orden {order_id}: {exc}")
            errors += 1

    # 4. Desconectar
    try:
        await ib.disconnect()
    except Exception as exc:
        _log.warning(f"Error desconectando de IBKR: {exc}")

    _log.info(
        f"Sincronización completada: {synced} órdenes sincronizadas, {errors} errores"
    )

    return {
        "pending_orders": len(pending),
        "synced": synced,
        "errors": errors,
        "updates": updates,
    }


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


async def main_async(args: argparse.Namespace) -> int:
    """Async main — sincroniza y espera interval para siguiente ciclo."""
    import time

    interval = args.interval  # segundos

    while True:
        start = time.time()

        try:
            result = await sync_order_status(
                vault_db_path=args.vault_db,
                host=args.host,
                port=args.port,
                client_id=args.client_id,
            )

            _log.info(
                f"Sync completado: {result['synced']} órdenes, {result['errors']} errores"
            )

            if args.once:
                return 0 if result["errors"] == 0 else 1

        except Exception as exc:
            _log.error(f"Error en sync loop: {exc}")
            if args.once:
                return 1

        elapsed = time.time() - start
        sleep_time = max(0, interval - elapsed)

        if sleep_time > 0:
            _log.debug(f"Esperando {sleep_time:.1f}s hasta próximo ciclo...")
            await asyncio.sleep(sleep_time)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="IBKR Order Monitor — sincroniza estado de órdenes desde el broker"
    )
    parser.add_argument(
        "--vault-db",
        required=True,
        help="Path al DuckDB vault (quant_traderdb1.duckdb)",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="IBKR Gateway host (default: IBKR_HOST env var)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="IBKR Gateway port (default: IBKR_PORT env var)",
    )
    parser.add_argument(
        "--client-id",
        type=int,
        default=None,
        help="Client ID (default: IBKR_CLIENT_ID env var)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Segundos entre sincronizaciones (default: 60)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Correr una vez y salir (no loop continuo)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Logging verboso (DEBUG)",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _log.info("IBKR Order Monitor iniciado")
    _log.info(f"Vault DB: {args.vault_db}")
    _log.info(f"Interval: {args.interval}s")
    _log.info(f"Once: {args.once}")

    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        _log.info("Detenido por usuario (Ctrl+C)")
        return 0
    except Exception as exc:
        _log.error(f"Error fatal: {exc}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
