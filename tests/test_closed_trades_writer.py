"""Tests for InsertClosedTradeCommand + closed_trades write handler."""

from __future__ import annotations

import uuid
from pathlib import Path

import duckdb
import pytest


@pytest.fixture()
def vault_with_closed_trades(tmp_path: Path):
    from duckclaw.schema_migrations import ensure_closed_trades_schema

    path = str(tmp_path / "vault.duckdb")
    ensure_closed_trades_schema(path)
    return path


def test_ensure_closed_trades_schema_idempotent(tmp_path: Path):
    from duckclaw.schema_migrations import ensure_closed_trades_schema

    path = str(tmp_path / "v.duckdb")
    ensure_closed_trades_schema(path)
    ensure_closed_trades_schema(path)
    con = duckdb.connect(path, read_only=True)
    try:
        n = con.execute("SELECT COUNT(*) FROM quant_core.closed_trades").fetchone()[0]
        assert n == 0
        cols = {
            r[1]
            for r in con.execute("PRAGMA table_info('quant_core.closed_trades')").fetchall()
        }
        assert {
            "signal_id",
            "session_uid",
            "ticker",
            "closed_at",
            "pnl",
            "ret_pct",
            "qty",
            "entry_px",
            "exit_px",
            "side",
            "fill_id",
        } <= cols
    finally:
        con.close()


def test_insert_closed_trade_handler_idempotent(vault_with_closed_trades: str):
    from duckclaw.write_command_handlers import dispatch_command

    path = vault_with_closed_trades
    payload = {
        "command_type": "insert_closed_trade",
        "ticker": "aapl",
        "fill_id": "11|2026-09-22T15:00:00|10|101.5",
        "closed_at": "2026-09-22T15:00:00",
        "qty": 10.0,
        "entry_px": 100.0,
        "exit_px": 101.5,
        "pnl": 15.0,
        "ret_pct": 0.015,
        "side": "LONG",
        "session_uid": "sess-1",
        "signal_id": str(uuid.uuid4()),
    }
    con = duckdb.connect(path)
    try:
        con.execute("BEGIN TRANSACTION")
        dispatch_command(con, payload)
        dispatch_command(con, payload)
        con.execute("COMMIT")
        n = con.execute("SELECT COUNT(*) FROM quant_core.closed_trades").fetchone()[0]
        assert n == 1
        row = con.execute(
            "SELECT ticker, side, qty, fill_id, pnl FROM quant_core.closed_trades"
        ).fetchone()
        assert row[0] == "AAPL"
        assert row[1] == "LONG"
        assert row[2] == 10.0
        assert row[3] == payload["fill_id"]
        assert row[4] == 15.0
    finally:
        con.close()


def test_insert_closed_trade_without_signal_id(vault_with_closed_trades: str):
    from duckclaw.write_command_handlers import dispatch_command

    path = vault_with_closed_trades
    payload = {
        "command_type": "insert_closed_trade",
        "ticker": "MSFT",
        "fill_id": "22|ts|5|198",
        "closed_at": "2026-09-22T16:00:00",
        "qty": -5.0,
        "entry_px": 200.0,
        "exit_px": 198.0,
        "pnl": 10.0,
        "ret_pct": 0.01,
        "side": "SHORT",
        "signal_id": "",
    }
    con = duckdb.connect(path)
    try:
        con.execute("BEGIN TRANSACTION")
        dispatch_command(con, payload)
        con.execute("COMMIT")
        sid = con.execute("SELECT signal_id FROM quant_core.closed_trades").fetchone()[0]
        assert sid is None
        side = con.execute("SELECT side FROM quant_core.closed_trades").fetchone()[0]
        assert side == "SHORT"
    finally:
        con.close()


def test_enqueue_closed_trade_recorded_uses_vault_db_path(tmp_path: Path, monkeypatch):
    from duckclaw.closed_trade_enqueue import enqueue_closed_trade_recorded
    from duckclaw.schema_migrations import ensure_closed_trades_schema

    vault = str(tmp_path / "vault.duckdb")
    ensure_closed_trades_schema(vault)
    captured: list[tuple[str, str]] = []

    def _capture(cmd, *, db_path, user_id="default", queue_name=None):
        captured.append((cmd.command_type, db_path))
        return "task-ct-1"

    monkeypatch.setattr(
        "duckclaw.db_write_queue.enqueue_typed_command",
        _capture,
    )
    mut = {
        "ticker": "CEG",
        "fill_id": "99|ts|3|50",
        "closed_at": "2026-09-22T12:00:00",
        "qty": 3.0,
        "entry_px": 48.0,
        "exit_px": 50.0,
        "pnl": 6.0,
        "ret_pct": 0.041666,
        "side": "LONG",
        "session_uid": "sess-x",
        "signal_id": "",
    }
    tid = enqueue_closed_trade_recorded(
        mut, db_path=vault, user_id="1726618406", tenant_id="default"
    )
    assert tid == "task-ct-1"
    assert captured == [("insert_closed_trade", vault)]


def test_m040_applied_by_run_pending_migrations(tmp_path: Path):
    from duckclaw.schema_migrations import run_pending_migrations

    path = str(tmp_path / "hub.duckdb")
    con = duckdb.connect(path)
    try:
        applied = run_pending_migrations(con)
        assert any("closed_trades" in name for name in applied)
        n = con.execute("SELECT COUNT(*) FROM quant_core.closed_trades").fetchone()[0]
        assert n == 0
    finally:
        con.close()
