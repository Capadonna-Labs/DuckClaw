from __future__ import annotations

import json

import duckdb

from duckclaw.graphs.on_the_fly_commands import (
    TradingSessionGoal,
    build_goals_proactive_system_event_message,
    _parse_trading_session_cli,
    _session_goal_from_cli,
    _execute_signal_verify_ledger,
    _looks_like_hallucinated_placeholder_uuid,
    _compute_trading_session_pnl_now,
    _dedupe_trading_session_snapshots,
    _quant_core_trade_signals_column_names,
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


def test_dedupe_trading_session_snapshots_consecutive_equal() -> None:
    assert _dedupe_trading_session_snapshots([-217.64, -217.64, -217.64]) == [-217.64]
    assert _dedupe_trading_session_snapshots([100.0, 200.0, 200.0, 300.0]) == [100.0, 200.0, 300.0]


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
