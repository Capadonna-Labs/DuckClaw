"""Protective BRACKET/OCA must never market-enter (Error #2 / XLU)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_is_protective_signal_type_variants():
    from duckclaw.signal_execution_bridge import (
        is_protective_signal_type,
        refuse_protective_as_market_entry,
        text_indicates_protective_order,
    )

    assert is_protective_signal_type("BRACKET")
    assert is_protective_signal_type("oca")
    assert is_protective_signal_type("PROTECTIVE_OCA")
    assert is_protective_signal_type("BRACKET_OCA")
    assert not is_protective_signal_type("ENTRY")
    assert not is_protective_signal_type("EXIT")
    assert not is_protective_signal_type(None)

    blocked = refuse_protective_as_market_entry("BRACKET")
    assert blocked is not None
    assert blocked["error"] == "BLOCKED_PROTECTIVE_ORDER_ROUTE"
    assert refuse_protective_as_market_entry("ENTRY") is None

    assert text_indicates_protective_order("place BRACKET OCA for XLU")
    assert not text_indicates_protective_order("ENTRY buy XLU 5%")


def test_execute_signal_with_bracket_routes_protective(tmp_path):
    vault = str(tmp_path / "vault.duckdb")
    enqueued = []

    def _capture(cmd, *, db_path, user_id="default", queue_name=None):
        enqueued.append((cmd.command_type, db_path, getattr(cmd, "notes", None)))
        return "task-p"

    protective_result = {
        "main_order_id": None,
        "tp_order_id": 101,
        "sl_order_id": 102,
        "status": "submitted",
        "timestamp": datetime.now(timezone.utc),
        "ticker": "XLU",
        "side": "BUY",
        "quantity": 1305,
        "oca_group": "PROTECT_XLU_1",
        "tp_price": 44.0,
        "sl_price": 38.0,
    }
    submit_bracket = AsyncMock(
        side_effect=AssertionError("must not call submit_bracket_order for BRACKET")
    )

    class _Result:
        def fetchone(self):
            return (44.0, 38.0)

    class _Con:
        def execute(self, *a, **k):
            return _Result()

        def close(self):
            return None

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
                "duckclaw.ibkr_bracket_orders.submit_protective_oca_orders",
                new_callable=AsyncMock,
                return_value=protective_result,
            ),
            patch(
                "duckclaw.ibkr_bracket_orders.submit_bracket_order",
                new=submit_bracket,
            ),
            patch(
                "duckclaw.db_write_queue.enqueue_typed_command",
                side_effect=_capture,
            ),
        ):
            from duckclaw.signal_execution_bridge import execute_signal_with_bracket

            return await execute_signal_with_bracket(
                signal_id="sig_bracket_xlu",
                ticker="XLU",
                side="BUY",
                quantity=1305,
                vault_db_path=vault,
                signal_type="BRACKET",
            )

    result = asyncio.run(_run())
    assert result["status"] == "submitted"
    assert result["main_order_id"] is None
    assert result["tp_order_id"] == 101
    assert result["sl_order_id"] == 102
    assert result.get("route") == "protective_oca"
    assert submit_bracket.await_count == 0
    assert any(c == "insert_ibkr_order" for c, _, _ in enqueued)
    assert any(c == "update_trade_signal_executed" for c, _, _ in enqueued)
    assert all(db == vault for _, db, _ in enqueued)


def test_execute_protective_refuses_without_tp_sl(tmp_path):
    vault = str(tmp_path / "vault.duckdb")

    class _Result:
        def fetchone(self):
            return None

    class _Con:
        def execute(self, *a, **k):
            return _Result()

        def close(self):
            return None

    async def _run():
        with patch("duckdb.connect", return_value=_Con()):
            from duckclaw.signal_execution_bridge import execute_protective_oca_for_signal

            return await execute_protective_oca_for_signal(
                signal_id="sig_no_levels",
                ticker="XLU",
                position_side="BUY",
                quantity=100,
                vault_db_path=vault,
            )

    result = asyncio.run(_run())
    assert result["status"] == "error"
    assert "ACTIVE tp_sl_levels" in result["error"]


def test_blocked_protective_broker_route_execute_approved():
    from duckclaw.workers.protective_order_route_guard import (
        blocked_protective_broker_route,
    )

    # ENTRY ok
    assert (
        blocked_protective_broker_route(
            "execute_approved_signal",
            {"signal_id": "abc", "signal_type": "ENTRY"},
        )
        is None
    )

    blocked = blocked_protective_broker_route(
        "execute_broker_signals_batch",
        {"signals": [{"signal_id": "x", "signal_type": "BRACKET"}]},
    )
    assert blocked is not None
    payload = json.loads(blocked)
    assert payload["error"] == "BLOCKED_PROTECTIVE_ORDER_ROUTE"
    assert payload["tool"] == "execute_broker_signals_batch"

    # Keyword in rationale without explicit ENTRY
    blocked2 = blocked_protective_broker_route(
        "run_quant_signal_cycle",
        {"ticker": "XLU", "rationale": "place protective BRACKET OCA TP/SL"},
    )
    assert blocked2 is not None


def test_blocked_protective_peeks_db_signal_type():
    from duckclaw.workers.protective_order_route_guard import (
        blocked_protective_broker_route,
    )

    class _Rows:
        def fetchall(self):
            return [("BRACKET",)]

    class _Db:
        def execute(self, *a, **k):
            return _Rows()

    blocked = blocked_protective_broker_route(
        "execute_approved_signal",
        {"signal_id": "sig-1"},
        db=_Db(),
    )
    assert blocked is not None
    assert json.loads(blocked)["signal_type"] == "BRACKET"


def test_patch_capadonna_broker_execute_bracket(tmp_path):
    import importlib.util
    import sys
    from pathlib import Path

    root = tmp_path / "Capadonna-Driller"
    target = root / "scripts" / "capadonna" / "broker_execute_signal.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        '''
def _plan_from_embedded():
        st = str(d.get("signal_type") or "ENTRY").strip().upper()
        if st not in ("ENTRY", "EXIT"):
            st = "ENTRY"
        return _WeightPlan(ticker=tkr, signal_type=st, weight_pct=w)

async def main_async():
        ticker = plan.ticker
        signal_type = plan.signal_type
        weight_pct = plan.weight_pct
        contract = Stock(ticker, "SMART", "USD")
        await ib.qualifyContractsAsync(contract)
''',
        encoding="utf-8",
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "patch_capadonna_broker_execute_bracket.py"
    spec = importlib.util.spec_from_file_location("patch_capadonna_broker_execute_bracket", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    old = sys.argv
    try:
        sys.argv = ["patch", "--root", str(root)]
        assert mod.main() == 0
        text = target.read_text(encoding="utf-8")
        assert "BLOCKED_PROTECTIVE_ORDER_ROUTE" in text
        assert 'st = "ENTRY"' not in text
        # Idempotent
        assert mod.main() == 0
    finally:
        sys.argv = old
