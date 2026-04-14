from __future__ import annotations

import json

from duckclaw.forge.skills.quant_tool_context import (
    note_quant_market_evidence_ticker,
    set_quant_tool_chat_id,
    set_quant_tool_db_path,
    set_quant_tool_tenant_id,
    set_quant_tool_user_id,
)
from duckclaw.forge.skills.quant_trader_bridge import (
    _execute_approved_signal_impl,
    _propose_trade_signal_impl,
)


class _FakeDb:
    def __init__(self) -> None:
        self._path = "/tmp/test_quant_trader.duckdb"

    def query(self, sql: str) -> str:
        if "SUM(balance)" in sql:
            return json.dumps([{"liquid": 10000.0}])
        if "FROM finance_worker.trade_signals" in sql:
            return json.dumps([{"human_approved": True, "status": "AWAITING_HITL"}])
        return json.dumps([])


def test_propose_trade_signal_requires_evidence(monkeypatch) -> None:
    db = _FakeDb()
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.push_quant_state_delta_sync",
        lambda payload: True,
    )
    out = json.loads(
        _propose_trade_signal_impl(
            db,
            mandate_id="11111111-1111-1111-1111-111111111111",
            ticker="SPY",
            weight=12.0,
            rationale="test",
        )
    )
    assert out["error"] == "EVIDENCE_UNIQUE_RULE"


def test_propose_trade_signal_applies_riskguard(monkeypatch) -> None:
    db = _FakeDb()
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    note_quant_market_evidence_ticker("SPY")
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge._max_weight_pct_limit",
        lambda: 10.0,
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.push_quant_state_delta_sync",
        lambda payload: True,
    )
    out = json.loads(
        _propose_trade_signal_impl(
            db,
            mandate_id="11111111-1111-1111-1111-111111111111",
            ticker="SPY",
            weight=12.0,
            rationale="base rationale",
        )
    )
    assert out["status"] == "AWAITING_HITL"
    assert out["proposed_weight"] == 10.0


def test_execute_approved_signal_requires_human_approval(monkeypatch) -> None:
    class _DbNoApproval(_FakeDb):
        def query(self, sql: str) -> str:
            if "FROM finance_worker.trade_signals" in sql:
                return json.dumps([{"human_approved": False, "status": "AWAITING_HITL"}])
            return super().query(sql)

    db = _DbNoApproval()
    set_quant_tool_chat_id("telegram_chat_1")
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.consume_execute_order_grant",
        lambda _cid, _sid: False,
    )
    out = json.loads(_execute_approved_signal_impl(db, signal_id="11111111-1111-1111-1111-111111111111"))
    assert out["error"] == "human_approved != TRUE"


def test_execute_approved_signal_accepts_telegram_grant(monkeypatch) -> None:
    class _DbNoApproval(_FakeDb):
        def query(self, sql: str) -> str:
            if "FROM finance_worker.trade_signals" in sql:
                return json.dumps([{"human_approved": False, "status": "AWAITING_HITL"}])
            return super().query(sql)

    db = _DbNoApproval()
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    set_quant_tool_chat_id("telegram_chat_1")
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.consume_execute_order_grant",
        lambda _cid, _sid: True,
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.push_quant_state_delta_sync",
        lambda _payload: True,
    )
    monkeypatch.delenv("IBKR_EXECUTE_ORDER_URL", raising=False)
    out = json.loads(_execute_approved_signal_impl(db, signal_id="11111111-1111-1111-1111-111111111111"))
    assert out["status"] == "simulated"
