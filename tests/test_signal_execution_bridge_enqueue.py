"""Ensure IBKR bridge/monitor enqueue typed commands with vault db_path."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


def test_execute_signal_with_bracket_enqueues_with_vault_db_path(tmp_path):
    vault = str(tmp_path / "vault.duckdb")

    class _Result:
        def fetchone(self):
            return (300.0, 245.0)

    class _Con:
        def execute(self, *a, **k):
            return _Result()

        def close(self):
            return None

    submit_result = {
        "main_order_id": 11,
        "tp_order_id": 12,
        "sl_order_id": 13,
        "status": "submitted",
        "timestamp": datetime.now(timezone.utc),
        "ticker": "CEG",
        "side": "BUY",
        "quantity": 10,
    }
    enqueued = []

    def _capture(cmd, *, db_path, user_id="default", queue_name=None):
        enqueued.append((cmd.command_type, db_path))
        return "task-1"

    ib = MagicMock()
    ib.disconnect = AsyncMock()

    async def _run():
        with (
            patch("duckdb.connect", return_value=_Con()),
            patch(
                "duckclaw.ibkr_bracket_orders.connect_ibkr",
                new_callable=AsyncMock,
                return_value=ib,
            ),
            patch(
                "duckclaw.ibkr_bracket_orders.submit_bracket_order",
                new_callable=AsyncMock,
                return_value=submit_result,
            ),
            patch(
                "duckclaw.db_write_queue.enqueue_typed_command",
                side_effect=_capture,
            ),
        ):
            from duckclaw.signal_execution_bridge import execute_signal_with_bracket

            return await execute_signal_with_bracket(
                signal_id="sig_1",
                ticker="CEG",
                side="BUY",
                quantity=10,
                vault_db_path=vault,
            )

    result = asyncio.run(_run())
    assert result["status"] == "submitted"
    assert len(enqueued) == 4
    assert all(db == vault for _, db in enqueued)
    types = {c for c, _ in enqueued}
    assert "insert_ibkr_order" in types
    assert "update_trade_signal_executed" in types


def test_sync_order_status_enqueues_with_vault_db_path(tmp_path):
    vault = str(tmp_path / "vault.duckdb")
    enqueued = []

    class _Result:
        def fetchall(self):
            return [(42, "CEG", "BUY", 10, "MARKET")]

    class _Con:
        def execute(self, *a, **k):
            return _Result()

        def close(self):
            return None

    def _capture(cmd, *, db_path, user_id="default", queue_name=None):
        enqueued.append((cmd.command_type, db_path, cmd.status, cmd.filled_qty))
        return "task-2"

    order_status = MagicMock()
    order_status.status = "Filled"
    order_status.filled = 10.0
    order_status.avgFillPrice = 301.5
    order_status.remaining = 0.0

    trade = MagicMock()
    trade.order.orderId = 42
    trade.orderStatus = order_status

    ib = MagicMock()
    ib.trades.return_value = [trade]
    ib.disconnect = AsyncMock()

    async def _run():
        with (
            patch("duckdb.connect", return_value=_Con()),
            patch(
                "duckclaw.ibkr_bracket_orders.connect_ibkr",
                new_callable=AsyncMock,
                return_value=ib,
            ),
            patch(
                "duckclaw.db_write_queue.enqueue_typed_command",
                side_effect=_capture,
            ),
        ):
            from duckclaw.ibkr_order_monitor import sync_order_status

            return await sync_order_status(vault_db_path=vault, client_id=99)

    result = asyncio.run(_run())
    assert result["synced"] == 1
    assert len(enqueued) == 1
    assert enqueued[0][0] == "update_ibkr_order_status"
    assert enqueued[0][1] == vault
    assert enqueued[0][2] == "filled"
    assert enqueued[0][3] == 10
