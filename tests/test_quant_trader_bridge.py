from __future__ import annotations

import json
import urllib.error

from duckclaw.forge.skills.quant_tool_context import (
    note_quant_market_evidence_ticker,
    set_quant_tool_chat_id,
    set_quant_tool_db_path,
    set_quant_tool_tenant_id,
    set_quant_tool_user_id,
)
from duckclaw.forge.skills.quant_trader_bridge import (
    _evaluate_cfd_state_impl,
    _execute_approved_signal_impl,
    _propose_trade_signal_impl,
)


class _FakeDb:
    def __init__(self) -> None:
        self._path = "/tmp/test_quant_trader.duckdb"

    def query(self, sql: str) -> str:
        if "SUM(balance)" in sql:
            return json.dumps([{"liquid": 10000.0}])
        if "trading_sessions" in sql:
            return json.dumps([{"mode": "paper"}])
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
    assert out["status"] == "PENDING_HITL"
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
    assert out.get("paper") is True


def test_execute_approved_signal_live_session_requires_env_live(monkeypatch) -> None:
    class _DbLive(_FakeDb):
        def query(self, sql: str) -> str:
            if "trading_sessions" in sql:
                return json.dumps([{"mode": "live"}])
            if "FROM finance_worker.trade_signals" in sql:
                return json.dumps([{"human_approved": True, "status": "AWAITING_HITL"}])
            return super().query(sql)

    db = _DbLive()
    set_quant_tool_chat_id("c1")
    monkeypatch.setenv("IBKR_ACCOUNT_MODE", "paper")
    out = json.loads(_execute_approved_signal_impl(db, signal_id="11111111-1111-1111-1111-111111111111"))
    assert out["error"] == "TRADING_SESSION_LIVE_REQUIRES_IBKR_ACCOUNT_MODE_LIVE"


def test_propose_trade_signal_blocked_on_drawdown_breach(monkeypatch) -> None:
    class _DbRisk(_FakeDb):
        def query(self, sql: str) -> str:
            if "trading_risk_constraints" in sql:
                return json.dumps([{"max_drawdown_pct": 0.05}])
            if "trading_sessions" in sql and "peak_equity" in sql:
                return json.dumps([{"status": "ACTIVE", "peak_equity": 100.0}])
            return super().query(sql)

    db = _DbRisk()
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    note_quant_market_evidence_ticker("SPY")
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.fetch_ibkr_total_equity_numeric",
        lambda: (85.0, ""),
    )
    out = json.loads(
        _propose_trade_signal_impl(
            db,
            mandate_id="11111111-1111-1111-1111-111111111111",
            ticker="SPY",
            weight=5.0,
        )
    )
    assert out["error"] == "RISK_GOAL_BREACH"


def test_propose_trade_signal_fails_closed_without_equity_when_dd_cap(monkeypatch) -> None:
    class _DbRisk(_FakeDb):
        def query(self, sql: str) -> str:
            if "trading_risk_constraints" in sql:
                return json.dumps([{"max_drawdown_pct": 0.05}])
            if "trading_sessions" in sql and "peak_equity" in sql:
                return json.dumps([{"status": "ACTIVE", "peak_equity": 100.0}])
            return super().query(sql)

    db = _DbRisk()
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    note_quant_market_evidence_ticker("SPY")
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.fetch_ibkr_total_equity_numeric",
        lambda: (None, "no API"),
    )
    out = json.loads(
        _propose_trade_signal_impl(
            db,
            mandate_id="11111111-1111-1111-1111-111111111111",
            ticker="SPY",
            weight=5.0,
        )
    )
    assert out["error"] == "RISK_EQUITY_UNAVAILABLE"


def test_execute_approved_signal_broker_error_pushes_failed(monkeypatch) -> None:
    class _DbNoSess(_FakeDb):
        def query(self, sql: str) -> str:
            if "trading_sessions" in sql:
                return json.dumps([])
            return super().query(sql)

    db = _DbNoSess()
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    set_quant_tool_chat_id("telegram_chat_1")
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.consume_execute_order_grant",
        lambda _cid, _sid: True,
    )
    monkeypatch.setenv("IBKR_ACCOUNT_MODE", "paper")
    monkeypatch.setenv("IBKR_EXECUTE_ORDER_URL", "http://127.0.0.1:9/order")

    payloads: list = []

    def _capture(p: dict) -> bool:
        payloads.append(p)
        return True

    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.push_quant_state_delta_sync",
        _capture,
    )

    def _boom(*_a, **_k):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr("duckclaw.forge.skills.quant_trader_bridge.urllib.request.urlopen", _boom)
    out = json.loads(_execute_approved_signal_impl(db, signal_id="11111111-1111-1111-1111-111111111111"))
    assert "error" in out
    assert any(p.get("delta_type") == "TRADE_SIGNAL_FAILED" for p in payloads)


def test_evaluate_cfd_state_no_active_session() -> None:
    class _DbNoSession(_FakeDb):
        def query(self, sql: str) -> str:
            if "trading_sessions" in sql:
                return json.dumps([])
            return super().query(sql)

    out = json.loads(
        _evaluate_cfd_state_impl(
            _DbNoSession(),
            session_uid="uid-1",
            tickers=["NVDA", "SPY"],
            signal_threshold="GAS",
        )
    )
    assert out["session_active"] is False
