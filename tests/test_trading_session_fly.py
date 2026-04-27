from __future__ import annotations

import json

import duckdb
import pytest

from duckclaw.graphs.on_the_fly_commands import (
    TradingSessionGoal,
    build_goals_proactive_system_event_message,
    _parse_quant_cycle_cli,
    _parse_trading_session_cli,
    _session_goal_from_cli,
    _execute_signal_verify_ledger,
    _looks_like_hallucinated_placeholder_uuid,
    _compute_trading_session_pnl_now,
    _dedupe_trading_session_snapshots,
    _quant_core_trade_signals_column_names,
    _TRADING_SESSION_PNL_HIST_UID_KEY,
    _TRADING_SESSION_PNL_SNAPSHOTS_KEY,
    _trading_session_snapshots_for_tearsheet_label,
    _trading_session_coalesce_unreliable_pnl_tick,
    _compute_trading_session_pnl_now_with_confidence,
    execute_quant_cycle,
    execute_quant_execute_signal,
    pop_fly_outbound_chart_b64,
    register_fly_outbound_chart_b64,
)


def test_parse_trading_session_cli_paper_tickers() -> None:
    parsed, err = _parse_trading_session_cli("--mode paper --tickers aapl,NVDA,AAPL")
    assert err is None and parsed is not None
    assert parsed.mode == "paper"
    assert parsed.tickers_csv == "AAPL,NVDA"
    assert parsed.confirm is False


def test_parse_trading_session_cli_live_requires_confirm_message() -> None:
    parsed, err = _parse_trading_session_cli("--mode live --tickers TSLA")
    assert err is None and parsed is not None
    assert parsed.mode == "live"
    assert parsed.confirm is False


def test_parse_trading_session_cli_live_confirmed() -> None:
    parsed, err = _parse_trading_session_cli("--mode live --confirm")
    assert err is None and parsed is not None
    assert parsed.mode == "live"
    assert parsed.confirm is True


def test_parse_trading_session_cli_missing_mode() -> None:
    parsed, err = _parse_trading_session_cli("--tickers SPY")
    assert parsed is None and err


def test_parse_trading_session_cli_status_stop_modes() -> None:
    p_status, err_status = _parse_trading_session_cli("--status")
    assert err_status is None and p_status is not None and p_status.status is True
    p_stop, err_stop = _parse_trading_session_cli("--stop")
    assert err_stop is None and p_stop is not None and p_stop.stop is True


def test_parse_quant_cycle_cli_defaults_and_valid_flags() -> None:
    parsed, err = _parse_quant_cycle_cli(
        "--tickers nvda,SPY --timeframe 4h --lookback_days 30 --objective rebalance_hrp --execute auto --signal gas --weight 7.5"
    )
    assert err is None and parsed is not None
    assert parsed.tickers_csv == "NVDA,SPY"
    assert parsed.timeframe == "4h"
    assert parsed.lookback_days == 30
    assert parsed.objective == "rebalance_hrp"
    assert parsed.execute == "auto"
    assert parsed.signal_threshold == "GAS"
    assert abs(parsed.weight_pct - 7.5) < 1e-9


def test_parse_quant_cycle_cli_invalid_execute() -> None:
    parsed, err = _parse_quant_cycle_cli("--tickers NVDA --execute now")
    assert parsed is None
    assert "execute" in (err or "").lower()


def test_execute_quant_cycle_structured_output(monkeypatch) -> None:
    class _Db:
        _path = "/tmp/test-quant-cycle.duckdb"

        def query(self, sql: str) -> str:
            if "FROM quant_core.trading_sessions" in sql:
                return json.dumps([{"session_uid": "sess-1", "tickers": "NVDA"}])
            return json.dumps([])

    def _fake_fetch(db, *, ticker: str, timeframe: str, lookback_days: int) -> str:
        _ = (db, timeframe, lookback_days)
        return json.dumps({"status": "ok", "ticker": ticker, "rows_upserted": 12})

    def _fake_portfolio() -> str:
        return "portfolio ok"

    def _fake_eval(db, *, session_uid: str, tickers: list[str], signal_threshold: str) -> str:
        _ = (db, signal_threshold)
        return json.dumps(
            {
                "outcome": "ACTIONABLE",
                "session_uid": session_uid,
                "results": [
                    {
                        "ticker": tickers[0],
                        "ok": True,
                        "phase_rank": 3,
                        "threshold_rank": 2,
                        "has_pending_hitl": False,
                    }
                ],
            }
        )

    def _fake_signal(
        db,
        *,
        mandate_id: str,
        ticker: str,
        weight: float,
        rationale: str,
        signal_type: str,
        execute_now: bool,
    ) -> str:
        _ = (db, mandate_id, weight, rationale, signal_type, execute_now)
        return json.dumps({"status": "PENDING_HITL", "signal_id": "11111111-1111-1111-1111-111111111111"})

    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_market_bridge._fetch_ib_gateway_ohlcv_impl",
        _fake_fetch,
    )
    monkeypatch.setattr("duckclaw.forge.skills.ibkr_bridge._get_ibkr_portfolio_impl", _fake_portfolio)
    monkeypatch.setattr("duckclaw.forge.skills.quant_trader_bridge._evaluate_cfd_state_impl", _fake_eval)
    monkeypatch.setattr("duckclaw.forge.skills.quant_trader_bridge._run_quant_signal_cycle_impl", _fake_signal)

    out = execute_quant_cycle(_Db(), "chat-1", "--tickers NVDA --execute auto", tenant_id="t1")
    assert "Ciclo Quant determinista ejecutado." in out
    assert "```json" in out
    payload = json.loads(out.split("```json\n", 1)[1].split("\n```", 1)[0])
    assert payload["command"] == "quant_cycle"
    assert payload["session_uid"] == "sess-1"
    assert payload["stages"]["signal"]["signal_id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["policy_decision"] == "HITL_REQUIRED"


def test_fly_outbound_chart_register_pop() -> None:
    register_fly_outbound_chart_b64(999001, "aaa")
    assert pop_fly_outbound_chart_b64(999001) == "aaa"
    assert pop_fly_outbound_chart_b64(999001) is None
    register_fly_outbound_chart_b64(999001, "   ")
    assert pop_fly_outbound_chart_b64(999001) is None


def test_quant_core_trade_signals_column_names() -> None:
    class D:
        def query(self, sql: str) -> str:
            if "table_info" in sql:
                return json.dumps(
                    [
                        {"name": "status"},
                        {"name": "session_uid"},
                    ]
                )
            return json.dumps([])

    assert _quant_core_trade_signals_column_names(D()) == {"status", "session_uid"}


def test_compute_trading_session_pnl_from_trade_signals_sum() -> None:
    uid = "a7c81171-7aea-4893-9852-a6dbe088e1d4"

    class D:
        def query(self, sql: str) -> str:
            if "table_info('quant_core.trade_signals')" in sql:
                return json.dumps([{"name": "unrealized_pnl"}, {"name": "session_uid"}])
            if "SUM(unrealized_pnl)" in sql and "trade_signals" in sql:
                return json.dumps([{"s": 12.25}])
            return json.dumps([])

    assert abs(_compute_trading_session_pnl_now(D(), uid) - 12.25) < 1e-6


def test_trading_session_coalesce_unreliable_uses_prev() -> None:
    assert _trading_session_coalesce_unreliable_pnl_tick(0.0, False, 400.0) == 400.0
    assert _trading_session_coalesce_unreliable_pnl_tick(0.0, True, 400.0) == 0.0
    assert _trading_session_coalesce_unreliable_pnl_tick(0.0, False, None) == 0.0


def test_compute_trading_session_pnl_unreliable_when_ibkr_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid = "a7c81171-7aea-4893-9852-a6dbe088e1d4"

    class D:
        def query(self, sql: str) -> str:
            if "table_info('quant_core.trade_signals')" in sql:
                return json.dumps([{"name": "unrealized_pnl"}, {"name": "session_uid"}])
            if "SUM(unrealized_pnl)" in sql and "trade_signals" in sql:
                return json.dumps([{"s": 0.0}])
            if "portfolio_positions" in sql:
                return json.dumps([{"s": 0.0}])
            return json.dumps([])

    def _ib_none() -> tuple[None, str]:
        return None, "gateway down"

    monkeypatch.setattr(
        "duckclaw.forge.skills.ibkr_bridge.fetch_ibkr_unrealized_pnl_total_numeric",
        _ib_none,
    )
    v, ok = _compute_trading_session_pnl_now_with_confidence(D(), uid)
    assert abs(v) < 1e-12
    assert ok is False


def test_dedupe_trading_session_snapshots_consecutive_equal() -> None:
    assert _dedupe_trading_session_snapshots([-217.64, -217.64, -217.64]) == [-217.64]
    assert _dedupe_trading_session_snapshots([100.0, 200.0, 200.0, 300.0]) == [100.0, 200.0, 300.0]


def test_trading_session_snapshots_for_tearsheet_label_empty_on_uid_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_get(db: object, chat_id: object, key: str) -> str:
        if key == _TRADING_SESSION_PNL_HIST_UID_KEY:
            return "other-uid"
        if key == _TRADING_SESSION_PNL_SNAPSHOTS_KEY:
            return "[1.0, 2.0, 3.0]"
        return ""

    monkeypatch.setattr("duckclaw.graphs.on_the_fly_commands.get_chat_state", _fake_get)
    class _Db:
        _path = "/tmp/x.duckdb"

    out = _trading_session_snapshots_for_tearsheet_label(
        _Db(), "c1", session_uid="want-this-uid"
    )
    assert out == []


def test_trading_session_snapshots_for_tearsheet_label_returns_deduped(monkeypatch: pytest.MonkeyPatch) -> None:
    uid = "a7c81171-7aea-4893-9852-a6dbe088e1d4"

    def _fake_get(db: object, chat_id: object, key: str) -> str:
        if key == _TRADING_SESSION_PNL_HIST_UID_KEY:
            return uid
        if key == _TRADING_SESSION_PNL_SNAPSHOTS_KEY:
            return "[100.0, 200.0, 200.0, 150.0]"
        return ""

    monkeypatch.setattr("duckclaw.graphs.on_the_fly_commands.get_chat_state", _fake_get)
    class _Db:
        _path = "/tmp/x.duckdb"

    got = _trading_session_snapshots_for_tearsheet_label(_Db(), "c1", session_uid=uid)
    assert got == [100.0, 200.0, 150.0]


def test_compute_trading_session_pnl_portfolio_positions_fallback() -> None:
    uid = "b1c81171-7aea-4893-9852-a6dbe088e1d4"

    class D:
        def query(self, sql: str) -> str:
            if "table_info('quant_core.trade_signals')" in sql:
                return json.dumps([{"name": "status"}])
            if "portfolio_positions" in sql:
                return json.dumps([{"s": 88.0}])
            return json.dumps([])

    assert abs(_compute_trading_session_pnl_now(D(), uid) - 88.0) < 1e-6


def test_session_goal_from_cli_defaults() -> None:
    parsed, err = _parse_trading_session_cli("--mode paper --tickers nvda,spy")
    assert err is None and parsed is not None
    goal = _session_goal_from_cli(parsed)
    assert isinstance(goal, TradingSessionGoal)
    assert goal.objective == "maximize_pnl"
    assert goal.signal_threshold == "GAS"
    assert goal.tickers == ["NVDA", "SPY"]


def test_parse_trading_session_objective_rebalance_hrp() -> None:
    parsed, err = _parse_trading_session_cli(
        "--mode paper --tickers SPY --objective rebalance_hrp"
    )
    assert err is None and parsed is not None
    assert parsed.objective == "rebalance_hrp"
    g = _session_goal_from_cli(parsed)
    assert g.objective == "rebalance_hrp"


def test_parse_trading_session_objective_invalid() -> None:
    parsed, err = _parse_trading_session_cli("--mode paper --objective foo")
    assert parsed is None and err and "objective" in (err or "").lower()


def test_build_goals_proactive_injects_rebalance_hrp() -> None:
    msg = build_goals_proactive_system_event_message(
        [{"belief_key": "x", "title": "Test"}],
        trading_session_objective="rebalance_hrp",
    )
    assert "rebalance_hrp" in msg
    assert "pesos HRP" in msg


def test_execute_signal_verify_quant_awaiting() -> None:
    class _Db:
        _path = "/tmp/x.duckdb"

        def query(self, sql: str) -> str:
            if "finance_worker.trade_signals" in sql:
                return json.dumps([{"status": "AWAITING_HITL"}])
            return json.dumps([])

    ok, msg = _execute_signal_verify_ledger(_Db(), "11111111-1111-1111-1111-111111111111")
    assert ok and not msg


def test_execute_signal_verify_quant_executed_rejected() -> None:
    class _Db:
        _path = "/tmp/x.duckdb"

        def query(self, sql: str) -> str:
            if "finance_worker.trade_signals" in sql:
                return json.dumps([{"status": "EXECUTED"}])
            return json.dumps([])

    ok, msg = _execute_signal_verify_ledger(_Db(), "11111111-1111-1111-1111-111111111111")
    assert not ok and "cerrada" in msg.lower()


def test_execute_signal_verify_finanz_quant_core_only() -> None:
    class _Db:
        _path = "/tmp/x.duckdb"

        def query(self, sql: str) -> str:
            if "finance_worker.trade_signals" in sql:
                return json.dumps([])
            if "quant_core.trade_signals" in sql:
                return json.dumps([{"signal_id": "22222222-2222-2222-2222-222222222222"}])
            return json.dumps([])

    ok, msg = _execute_signal_verify_ledger(_Db(), "22222222-2222-2222-2222-222222222222")
    assert ok and not msg


def test_looks_like_hallucinated_placeholder_uuid() -> None:
    assert _looks_like_hallucinated_placeholder_uuid("e0e5e5e5-5e5e-5e5e-5e5e-5e5e5e5e5e5e")
    assert not _looks_like_hallucinated_placeholder_uuid("990bdbe0-07a2-4abc-9ebd-756ebd08fca5")


def test_execute_quant_execute_signal_rejects_placeholder_uuid() -> None:
    out = execute_quant_execute_signal(None, "1", "e0e5e5e5-5e5e-5e5e-5e5e-5e5e5e5e5e5e")
    assert "propose_trade_signal" in out


def test_trading_session_upsert_sql_duckdb_prepared_safe() -> None:
    """Regression: CURRENT_TIMESTAMP + ? en la misma sentencia rompe el binder de DuckDB."""
    c = duckdb.connect(":memory:")
    c.execute(
        """
        CREATE SCHEMA IF NOT EXISTS quant_core;
        CREATE TABLE IF NOT EXISTS quant_core.trading_sessions (
          id VARCHAR PRIMARY KEY,
          mode VARCHAR NOT NULL,
          tickers VARCHAR NOT NULL DEFAULT '',
          session_uid VARCHAR,
          status VARCHAR NOT NULL DEFAULT 'ACTIVE',
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    upsert = """
INSERT INTO quant_core.trading_sessions (id, mode, tickers, session_uid, status)
VALUES (?, ?, ?, ?, 'ACTIVE')
ON CONFLICT (id) DO UPDATE SET
  mode = excluded.mode,
  tickers = excluded.tickers,
  session_uid = excluded.session_uid,
  status = 'ACTIVE',
  updated_at = now()
"""
    c.execute(upsert, ["active", "paper", "X", "uid-1"])
    row = c.execute(
        "SELECT mode, tickers, session_uid FROM quant_core.trading_sessions WHERE id = 'active'"
    ).fetchone()
    assert row == ("paper", "X", "uid-1")
