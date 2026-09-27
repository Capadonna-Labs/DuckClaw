from __future__ import annotations

import duckdb

from duckclaw.trade_signals_ledger import (
    fetch_trade_signal_row,
    fetch_trade_signal_row_from_path,
    mark_trade_signal_executed,
)


def _mk_vault(tmp_path, *, finance: bool = True, quant: bool = False):
    path = str(tmp_path / "vault.duckdb")
    con = duckdb.connect(path)
    if finance:
        con.execute("CREATE SCHEMA finance_worker")
        con.execute(
            """
            CREATE TABLE finance_worker.trade_signals (
                signal_id VARCHAR,
                action VARCHAR,
                strategy_name VARCHAR,
                rationale VARCHAR,
                order_qty DOUBLE,
                signal_type VARCHAR,
                ticker VARCHAR,
                executed_at TIMESTAMP
            )
            """
        )
        con.execute(
            """
            INSERT INTO finance_worker.trade_signals VALUES (
                'sig-mu-1', 'SELL', 'manual', 'reduce 15 MU', 15, 'EXIT', 'MU', NULL
            )
            """
        )
    if quant:
        con.execute("CREATE SCHEMA quant_core")
        con.execute(
            """
            CREATE TABLE quant_core.trade_signals (
                signal_id VARCHAR,
                action VARCHAR,
                strategy_name VARCHAR,
                rationale VARCHAR,
                order_qty DOUBLE,
                signal_type VARCHAR,
                ticker VARCHAR,
                executed_at TIMESTAMP
            )
            """
        )
        con.execute(
            """
            INSERT INTO quant_core.trade_signals VALUES (
                'sig-qc-1', 'BUY', 'cfd', 'entry', 10, 'ENTRY', 'XLU', NULL
            )
            """
        )
    con.close()
    return path


def test_fetch_prefers_finance_worker(tmp_path) -> None:
    path = _mk_vault(tmp_path, finance=True, quant=True)
    row = fetch_trade_signal_row_from_path(path, "sig-mu-1")
    assert row is not None
    assert row["schema"] == "finance_worker"
    assert row["ticker"] == "MU"
    assert row["signal_type"] == "EXIT"
    assert int(row["order_qty"]) == 15


def test_fetch_falls_back_to_quant_core(tmp_path) -> None:
    path = _mk_vault(tmp_path, finance=False, quant=True)
    row = fetch_trade_signal_row_from_path(path, "sig-qc-1")
    assert row is not None
    assert row["schema"] == "quant_core"
    assert row["ticker"] == "XLU"


def test_mark_executed_updates_finance_worker(tmp_path) -> None:
    path = _mk_vault(tmp_path, finance=True, quant=False)
    con = duckdb.connect(path)
    touched = mark_trade_signal_executed(con, "sig-mu-1", "2026-09-27T16:00:00+00:00")
    assert touched == ["finance_worker"]
    ts = con.execute(
        "SELECT executed_at FROM finance_worker.trade_signals WHERE signal_id='sig-mu-1'"
    ).fetchone()[0]
    con.close()
    assert ts is not None


def test_fetch_missing_returns_none(tmp_path) -> None:
    path = _mk_vault(tmp_path, finance=True, quant=False)
    assert fetch_trade_signal_row_from_path(path, "nope") is None
    con = duckdb.connect(path, read_only=True)
    try:
        assert fetch_trade_signal_row(con, "nope") is None
    finally:
        con.close()
