"""Ensure IBKR bridge/monitor enqueue typed commands with vault db_path."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb


def test_execute_signal_with_bracket_enqueues_with_vault_db_path(tmp_path):
    vault = str(tmp_path / "vault.duckdb")

    class _ResultTpSl:
        def fetchone(self):
            return (300.0, 245.0)

    class _ResultSignal:
        def fetchone(self):
            return ("BUY", "rebalance_hrp", "new entry", 10)

    class _Con:
        def execute(self, sql, *a, **k):
            if "trade_signals" in sql.lower():
                return _ResultSignal()
            return _ResultTpSl()

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


def test_execute_signal_with_bracket_refuses_bare_market_order(tmp_path):
    vault = str(tmp_path / "vault.duckdb")

    class _ResultTpSl:
        def fetchone(self):
            return None

    class _ResultSignal:
        def fetchone(self):
            return ("BUY", "rebalance_hrp", "new entry", 10)

    class _Con:
        def execute(self, sql, *a, **k):
            if "trade_signals" in sql.lower():
                return _ResultSignal()
            return _ResultTpSl()

        def close(self):
            return None

    async def _run():
        with (
            patch("duckdb.connect", return_value=_Con()),
            patch(
                "duckclaw.ibkr_bracket_orders.connect_ibkr",
                new_callable=AsyncMock,
            ) as connect,
        ):
            from duckclaw.signal_execution_bridge import execute_signal_with_bracket

            result = await execute_signal_with_bracket(
                signal_id="sig_1",
                ticker="XLU",
                side="BUY",
                quantity=10,
                vault_db_path=vault,
            )
            assert not connect.called
            return result

    result = asyncio.run(_run())
    assert result["status"] == "error"
    assert "without TP/SL" in result["error"]


def test_protective_signal_uses_protective_oca_not_entry_bracket(tmp_path):
    vault = str(tmp_path / "vault.duckdb")

    class _ResultTpSl:
        def fetchone(self):
            return (44.0, 38.0)

    class _ResultSignal:
        def fetchone(self):
            return ("BUY", "tp_sl_protection", "BRACKET OCA protectivo; no es entrada nueva", None)

    class _Con:
        def execute(self, sql, *a, **k):
            if "trade_signals" in sql.lower():
                return _ResultSignal()
            return _ResultTpSl()

        def close(self):
            return None

    protective_result = {
        "main_order_id": None,
        "tp_order_id": 21,
        "sl_order_id": 22,
        "status": "submitted",
        "timestamp": datetime.now(timezone.utc),
        "ticker": "XLU",
        "side": "BUY",
        "quantity": 1296,
        "oca_group": "PROTECT_XLU_1",
    }
    enqueued = []

    def _capture(cmd, *, db_path, user_id="default", queue_name=None):
        enqueued.append((cmd.command_type, getattr(cmd, "order_type", ""), db_path))
        return "task-1"

    ib = MagicMock()
    ib.positions.return_value = [
        MagicMock(contract=MagicMock(symbol="XLU"), position=1296)
    ]
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
            ) as entry_bracket,
            patch(
                "duckclaw.ibkr_bracket_orders.submit_protective_oca_orders",
                new_callable=AsyncMock,
                return_value=protective_result,
            ) as protective_oca,
            patch(
                "duckclaw.db_write_queue.enqueue_typed_command",
                side_effect=_capture,
            ),
        ):
            from duckclaw.signal_execution_bridge import execute_signal_with_bracket

            result = await execute_signal_with_bracket(
                signal_id="sig_1",
                ticker="XLU",
                side="BUY",
                quantity=1123,
                vault_db_path=vault,
            )
            assert not entry_bracket.called
            protective_oca.assert_awaited_once()
            assert protective_oca.await_args.args[3] == 1296
            return result

    result = asyncio.run(_run())
    assert result["status"] == "submitted"
    assert result["main_order_id"] is None
    assert len([x for x in enqueued if x[0] == "insert_ibkr_order"]) == 2
    assert ("insert_ibkr_order", "MARKET", vault) not in enqueued


def test_tools_node_blocks_protective_signal_from_entry_executor(tmp_path):
    vault = str(tmp_path / "vault.duckdb")
    con = duckdb.connect(vault)
    con.execute("CREATE SCHEMA quant_core")
    con.execute(
        """
        CREATE TABLE quant_core.trade_signals (
            signal_id UUID,
            strategy_name VARCHAR,
            rationale VARCHAR,
            signal_type VARCHAR
        )
        """
    )
    con.execute(
        """
        INSERT INTO quant_core.trade_signals VALUES (
            '63f57d0d-2769-48b5-a345-6abe3a65b9ec',
            'cfd_auto',
            'Bracket OCA 1,296 sh XLU — SL $38 / TP $44',
            'BRACKET'
        )
        """
    )
    con.close()

    from duckclaw.workers.protective_order_route_guard import blocked_protective_broker_route

    # Open RO connection like tools_node harness (db handle).
    db = duckdb.connect(vault, read_only=True)
    try:
        err = blocked_protective_broker_route(
            "execute_approved_signal",
            {"signal_id": "63f57d0d-2769-48b5-a345-6abe3a65b9ec"},
            db=db,
        )
    finally:
        db.close()
    assert err is not None
    assert "BLOCKED_PROTECTIVE_ORDER_ROUTE" in err


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
