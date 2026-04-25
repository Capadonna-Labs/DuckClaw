from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

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
    _normalize_proposed_weight_pct,
    _propose_trade_signal_impl,
)


def _trade_sig_row(**overrides: object) -> str:
    base: dict[str, object] = {
        "human_approved": True,
        "status": "AWAITING_HITL",
        "ticker": "SPY",
        "signal_type": "ENTRY",
        "proposed_weight": 5.0,
        "mandate_id": "33333333-3333-3333-3333-333333333333",
    }
    base.update(overrides)
    return json.dumps([base])


class _FakeDb:
    def __init__(self) -> None:
        self._path = "/tmp/test_quant_trader.duckdb"

    def query(self, sql: str) -> str:
        if "SUM(balance)" in sql:
            return json.dumps([{"liquid": 10000.0}])
        if "trading_sessions" in sql:
            return json.dumps([{"mode": "paper"}])
        if "FROM finance_worker.trade_signals" in sql:
            return _trade_sig_row()
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


def test_normalize_proposed_weight_pct_fraction() -> None:
    assert abs(_normalize_proposed_weight_pct(0.03) - 3.0) < 1e-9
    assert abs(_normalize_proposed_weight_pct(3.0) - 3.0) < 1e-9
    assert abs(_normalize_proposed_weight_pct(1.0) - 1.0) < 1e-9


def test_propose_trade_signal_interprets_llm_fraction_as_percent(monkeypatch) -> None:
    """0.03 (fracción tipo '3%') debe persistir como ~3% para el hook VPS."""
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
            weight=0.03,
            rationale="test",
        )
    )
    assert out["status"] == "PENDING_HITL"
    assert abs(float(out["proposed_weight"]) - 3.0) < 1e-9


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
                return _trade_sig_row(human_approved=False)
            return super().query(sql)

    db = _DbNoApproval()
    set_quant_tool_chat_id("telegram_chat_1")
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.consume_execute_order_grant",
        lambda _cid, _sid: False,
    )
    out = json.loads(_execute_approved_signal_impl(db, signal_id="11111111-1111-1111-1111-111111111111"))
    assert out["error"] == "human_approved != TRUE"


def test_execute_approved_signal_missing_placeholder_id_explains_ledger() -> None:
    """LLM-invented UUIDs (e.g. 0000ffff-…) are not in finance_worker.trade_signals."""

    class _NoRows:
        def query(self, sql: str) -> str:
            if "FROM finance_worker.trade_signals" in sql:
                return "[]"
            if "FROM quant_core.trade_signals" in sql:
                return "[]"
            return "[]"

    out = json.loads(
        _execute_approved_signal_impl(
            _NoRows(),
            signal_id="0000ffff-1111-2222-3333-444455556666",
        )
    )
    assert out["error"] == "signal no existe"
    assert out.get("reason") == "SIGNAL_ID_NOT_IN_LEDGER"
    assert "propose_trade_signal" in (out.get("message") or "")


def test_execute_approved_signal_accepts_telegram_grant(monkeypatch) -> None:
    class _DbNoApproval(_FakeDb):
        def query(self, sql: str) -> str:
            if "FROM finance_worker.trade_signals" in sql:
                return _trade_sig_row(human_approved=False)
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


def test_execute_approved_signal_sends_account_mode_header(monkeypatch) -> None:
    class _DbOk(_FakeDb):
        def query(self, sql: str) -> str:
            if "FROM finance_worker.trade_signals" in sql:
                return _trade_sig_row()
            return super().query(sql)

    captured: list[urllib.request.Request] = []

    def _fake_urlopen(req: urllib.request.Request, timeout: object = None) -> object:
        captured.append(req)

        class _Resp:
            def read(self) -> bytes:
                return b"{}"

            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        return _Resp()

    db = _DbOk()
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    set_quant_tool_chat_id("telegram_chat_1")
    monkeypatch.setenv("IBKR_EXECUTE_ORDER_URL", "http://127.0.0.1:9/order")
    monkeypatch.setenv("IBKR_ACCOUNT_MODE", "paper")
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.push_quant_state_delta_sync",
        lambda _payload: True,
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.urllib.request.urlopen",
        _fake_urlopen,
    )
    json.loads(_execute_approved_signal_impl(db, signal_id="11111111-1111-1111-1111-111111111111"))
    assert len(captured) == 1
    hdrs = {k.lower(): v for k, v in captured[0].header_items()}
    assert hdrs.get("x-duckclaw-ibkr-account-mode") == "paper"


def test_execute_approved_signal_post_includes_weight_payload(monkeypatch) -> None:
    class _DbOk(_FakeDb):
        def query(self, sql: str) -> str:
            if "FROM finance_worker.trade_signals" in sql:
                return _trade_sig_row(ticker="QQQ", proposed_weight=3.5)
            return super().query(sql)

    bodies: list[dict] = []

    def _fake_urlopen(req: urllib.request.Request, timeout: object = None) -> object:
        bodies.append(json.loads(req.data.decode("utf-8")))

        class _Resp:
            def read(self) -> bytes:
                return b"{}"

            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        return _Resp()

    db = _DbOk()
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    set_quant_tool_chat_id("telegram_chat_1")
    monkeypatch.setenv("IBKR_EXECUTE_ORDER_URL", "http://127.0.0.1:9/order")
    monkeypatch.setenv("IBKR_ACCOUNT_MODE", "paper")
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.push_quant_state_delta_sync",
        lambda _payload: True,
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.urllib.request.urlopen",
        _fake_urlopen,
    )
    json.loads(_execute_approved_signal_impl(db, signal_id="11111111-1111-1111-1111-111111111111"))
    assert bodies[0]["ticker"] == "QQQ"
    assert bodies[0]["proposed_weight"] == 3.5
    assert bodies[0]["signal_type"] == "ENTRY"


def test_execute_approved_signal_normalizes_fraction_weight_in_post(monkeypatch) -> None:
    class _DbFrac(_FakeDb):
        def query(self, sql: str) -> str:
            if "FROM finance_worker.trade_signals" in sql:
                return _trade_sig_row(ticker="META", proposed_weight=0.03)
            return super().query(sql)

    bodies: list[dict] = []

    def _fake_urlopen(req: urllib.request.Request, timeout: object = None) -> object:
        bodies.append(json.loads(req.data.decode("utf-8")))

        class _Resp:
            def read(self) -> bytes:
                return b'{"status":"success","qty":1,"ib_order_id":99}'

            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        return _Resp()

    db = _DbFrac()
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    set_quant_tool_chat_id("telegram_chat_1")
    monkeypatch.setenv("IBKR_EXECUTE_ORDER_URL", "http://127.0.0.1:9/order")
    monkeypatch.setenv("IBKR_ACCOUNT_MODE", "paper")
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.push_quant_state_delta_sync",
        lambda _payload: True,
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.urllib.request.urlopen",
        _fake_urlopen,
    )
    out = json.loads(_execute_approved_signal_impl(db, signal_id="11111111-1111-1111-1111-111111111111"))
    assert bodies[0]["proposed_weight"] == 3.0
    assert out.get("ib_order_id") == 99
    assert out.get("qty") == 1


def test_execute_approved_signal_live_sends_live_header(monkeypatch) -> None:
    class _DbLiveOk(_FakeDb):
        def query(self, sql: str) -> str:
            if "trading_sessions" in sql and "mode" in sql:
                return json.dumps([{"mode": "live"}])
            if "FROM finance_worker.trade_signals" in sql:
                return _trade_sig_row()
            return super().query(sql)

    captured: list[urllib.request.Request] = []

    def _fake_urlopen(req: urllib.request.Request, timeout: object = None) -> object:
        captured.append(req)

        class _Resp:
            def read(self) -> bytes:
                return b"{}"

            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        return _Resp()

    db = _DbLiveOk()
    set_quant_tool_chat_id("c1")
    monkeypatch.setenv("IBKR_EXECUTE_ORDER_URL", "http://127.0.0.1:9/order")
    monkeypatch.setenv("IBKR_ACCOUNT_MODE", "live")
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.push_quant_state_delta_sync",
        lambda _payload: True,
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.urllib.request.urlopen",
        _fake_urlopen,
    )
    json.loads(_execute_approved_signal_impl(db, signal_id="11111111-1111-1111-1111-111111111111"))
    assert len(captured) == 1
    hdrs = {k.lower(): v for k, v in captured[0].header_items()}
    assert hdrs.get("x-duckclaw-ibkr-account-mode") == "live"


def test_execute_approved_signal_live_session_requires_env_live(monkeypatch) -> None:
    class _DbLive(_FakeDb):
        def query(self, sql: str) -> str:
            if "trading_sessions" in sql:
                return json.dumps([{"mode": "live"}])
            if "FROM finance_worker.trade_signals" in sql:
                return _trade_sig_row()
            return super().query(sql)

    db = _DbLive()
    set_quant_tool_chat_id("c1")
    monkeypatch.setenv("IBKR_ACCOUNT_MODE", "paper")
    out = json.loads(_execute_approved_signal_impl(db, signal_id="11111111-1111-1111-1111-111111111111"))
    assert out["error"] == "TRADING_SESSION_LIVE_REQUIRES_IBKR_ACCOUNT_MODE_LIVE"


def test_execute_approved_signal_paper_session_allows_ibkr_env_live(monkeypatch) -> None:
    """Sesión paper debe ejecutar aunque IBKR_ACCOUNT_MODE sea live (header/post usan paper_flag)."""
    captured: list[urllib.request.Request] = []

    def _fake_urlopen(req: urllib.request.Request, timeout: object = None) -> object:
        captured.append(req)

        class _Resp:
            def read(self) -> bytes:
                return b"{}"

            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        return _Resp()

    db = _FakeDb()
    set_quant_tool_chat_id("c1")
    monkeypatch.setenv("IBKR_EXECUTE_ORDER_URL", "http://127.0.0.1:9/order")
    monkeypatch.setenv("IBKR_ACCOUNT_MODE", "live")
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.push_quant_state_delta_sync",
        lambda _payload: True,
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.urllib.request.urlopen",
        _fake_urlopen,
    )
    out = json.loads(_execute_approved_signal_impl(db, signal_id="11111111-1111-1111-1111-111111111111"))
    assert out.get("status") == "sent"
    assert len(captured) == 1
    hdrs = {k.lower(): v for k, v in captured[0].header_items()}
    assert hdrs.get("x-duckclaw-ibkr-account-mode") == "paper"
    body = json.loads(captured[0].data.decode("utf-8"))
    assert body.get("paper") is True


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


def test_execute_approved_signal_broker_timeout_returns_code(monkeypatch) -> None:
    db = _FakeDb()
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    set_quant_tool_chat_id("telegram_chat_1")
    monkeypatch.setenv("IBKR_ACCOUNT_MODE", "paper")
    monkeypatch.setenv("IBKR_EXECUTE_ORDER_URL", "http://127.0.0.1:9/order")
    monkeypatch.setenv("IBKR_EXECUTE_ORDER_TIMEOUT_SEC", "180")

    def _timed_out(*_a, **_k):
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr("duckclaw.forge.skills.quant_trader_bridge.urllib.request.urlopen", _timed_out)
    out = json.loads(_execute_approved_signal_impl(db, signal_id="11111111-1111-1111-1111-111111111111"))
    assert out.get("error") == "BROKER_TIMEOUT"
    assert out.get("timeout_sec") == 180


def test_execute_approved_signal_passes_timeout_to_urlopen(monkeypatch) -> None:
    captured: list[object] = []

    def _fake_urlopen(req: urllib.request.Request, timeout: object = None) -> object:
        captured.append(timeout)

        class _Resp:
            def read(self) -> bytes:
                return b"{}"

            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        return _Resp()

    db = _FakeDb()
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    set_quant_tool_chat_id("telegram_chat_1")
    monkeypatch.setenv("IBKR_EXECUTE_ORDER_URL", "http://127.0.0.1:9/order")
    monkeypatch.setenv("IBKR_EXECUTE_ORDER_TIMEOUT_SEC", "99")
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.push_quant_state_delta_sync",
        lambda _payload: True,
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.urllib.request.urlopen",
        _fake_urlopen,
    )
    json.loads(_execute_approved_signal_impl(db, signal_id="11111111-1111-1111-1111-111111111111"))
    assert captured == [99.0]


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


def test_execute_approved_signal_http_error_includes_broker_json_message(monkeypatch) -> None:
    db = _FakeDb()
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    monkeypatch.setenv("IBKR_ACCOUNT_MODE", "paper")
    monkeypatch.setenv("IBKR_EXECUTE_ORDER_URL", "http://127.0.0.1:9/order")

    def _http501(*_a, **_k):
        fp = io.BytesIO(
            b'{"status":"error","message":"Order execution hook not configured. Set OHLCV_EXECUTE_ORDER_PYTHON."}'
        )
        raise urllib.error.HTTPError("http://127.0.0.1:9/order", 501, "Not Implemented", {}, fp)

    monkeypatch.setattr("duckclaw.forge.skills.quant_trader_bridge.urllib.request.urlopen", _http501)
    out = json.loads(_execute_approved_signal_impl(db, signal_id="11111111-1111-1111-1111-111111111111"))
    assert out.get("error") == "Broker HTTP 501"
    assert "hook not configured" in (out.get("broker_message") or "").lower()


def test_propose_trade_signal_auto_execute_disabled_by_default(monkeypatch) -> None:
    """Sin DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS, la respuesta no encadena ejecución."""
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
            weight=5.0,
        )
    )
    assert out.get("status") == "PENDING_HITL"
    assert "auto_executed" not in out


def test_propose_auto_execute_skips_live_without_allow_live(monkeypatch) -> None:
    class _DbLive(_FakeDb):
        def query(self, sql: str) -> str:
            if "trading_sessions" in sql and "mode" in sql and "id = 'active'" in sql:
                return json.dumps([{"mode": "live"}])
            return super().query(sql)

    db = _DbLive()
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
        lambda _payload: True,
    )
    monkeypatch.setenv("DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS", "1")
    monkeypatch.delenv("DUCKCLAW_QUANT_AUTO_EXECUTE_ALLOW_LIVE", raising=False)
    out = json.loads(
        _propose_trade_signal_impl(
            db,
            mandate_id="11111111-1111-1111-1111-111111111111",
            ticker="SPY",
            weight=5.0,
        )
    )
    assert out.get("status") == "PENDING_HITL"
    assert out.get("auto_execute", {}).get("skipped") is True
    assert "auto_executed" not in out


def test_propose_auto_execute_paper_chains_to_simulated_execute(monkeypatch) -> None:
    class _DbPendingHitl(_FakeDb):
        def query(self, sql: str) -> str:
            if "FROM finance_worker.trade_signals" in sql and "human_approved" in sql:
                return _trade_sig_row(human_approved=False)
            return super().query(sql)

    db = _DbPendingHitl()
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    set_quant_tool_chat_id("tg_auto_exec_1")
    note_quant_market_evidence_ticker("SPY")
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge._max_weight_pct_limit",
        lambda: 10.0,
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.push_quant_state_delta_sync",
        lambda _payload: True,
    )
    monkeypatch.setenv("DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS", "1")
    monkeypatch.delenv("IBKR_EXECUTE_ORDER_URL", raising=False)
    out = json.loads(
        _propose_trade_signal_impl(
            db,
            mandate_id="11111111-1111-1111-1111-111111111111",
            ticker="SPY",
            weight=5.0,
        )
    )
    assert out.get("auto_executed") is True
    ex = out.get("execution")
    assert isinstance(ex, dict) and ex.get("status") == "simulated"


def test_propose_auto_execute_row_timeout_surfaces_error(monkeypatch) -> None:
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
        lambda _payload: True,
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge._wait_until_signal_row_visible",
        lambda _db, _sid, **kwargs: False,
    )
    monkeypatch.setenv("DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS", "1")
    out = json.loads(
        _propose_trade_signal_impl(
            db,
            mandate_id="11111111-1111-1111-1111-111111111111",
            ticker="SPY",
            weight=5.0,
        )
    )
    assert out.get("status") == "PENDING_HITL"
    assert out.get("auto_execute", {}).get("error") == "SIGNAL_ROW_TIMEOUT"
    assert "auto_executed" not in out
