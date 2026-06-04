"""Tests for /cancel_signal fly command (force clean ledger)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from duckclaw import DuckClaw
from duckclaw.graphs.on_the_fly_commands import (
    _parse_cancel_signal_args,
    _resolve_trade_signal_status,
    execute_cancel_signal,
)

_SIGNAL_FAILED = "a0000001-0000-4000-8000-000000000001"
_SIGNAL_EXECUTED = "b0000002-0000-4000-8000-000000000002"
_SIGNAL_EXPIRED = "c0000003-0000-4000-8000-000000000003"
_SIGNAL_QUANT_ONLY = "d0000004-0000-4000-8000-000000000004"


def _query_status(db: DuckClaw, sid: str, schema: str) -> str:
    qsid = sid.replace("'", "''")
    raw = db.query(
        f"SELECT status FROM {schema}.trade_signals WHERE signal_id = '{qsid}' LIMIT 1"
    )
    rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    if rows and isinstance(rows[0], dict):
        return str(rows[0].get("status") or "").strip().upper()
    return ""


@pytest.fixture
def ledger_db(tmp_path: Path) -> DuckClaw:
    path = str(tmp_path / "cancel_signal_test.duckdb")
    db = DuckClaw(path)
    db.execute("CREATE SCHEMA IF NOT EXISTS finance_worker")
    db.execute("CREATE SCHEMA IF NOT EXISTS quant_core")
    db.execute(
        """
        CREATE TABLE finance_worker.trade_signals (
            signal_id VARCHAR PRIMARY KEY,
            status VARCHAR
        )
        """
    )
    db.execute(
        """
        CREATE TABLE quant_core.trade_signals (
            signal_id VARCHAR PRIMARY KEY,
            status VARCHAR,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        "INSERT INTO finance_worker.trade_signals VALUES (?, ?)",
        [_SIGNAL_FAILED, "FAILED"],
    )
    db.execute(
        "INSERT INTO quant_core.trade_signals (signal_id, status) VALUES (?, ?)",
        [_SIGNAL_FAILED, "FAILED"],
    )
    db.execute(
        "INSERT INTO finance_worker.trade_signals VALUES (?, ?)",
        [_SIGNAL_EXECUTED, "EXECUTED"],
    )
    db.execute(
        "INSERT INTO quant_core.trade_signals (signal_id, status) VALUES (?, ?)",
        [_SIGNAL_EXECUTED, "EXECUTED"],
    )
    db.execute(
        "INSERT INTO finance_worker.trade_signals VALUES (?, ?)",
        [_SIGNAL_EXPIRED, "EXPIRED"],
    )
    db.execute(
        "INSERT INTO quant_core.trade_signals (signal_id, status) VALUES (?, ?)",
        [_SIGNAL_EXPIRED, "EXPIRED"],
    )
    db.execute(
        "INSERT INTO quant_core.trade_signals (signal_id, status) VALUES (?, ?)",
        [_SIGNAL_QUANT_ONLY, "FAILED"],
    )
    return db


def test_parse_cancel_signal_args_force_flag() -> None:
    sid, force, err = _parse_cancel_signal_args(f"{_SIGNAL_FAILED} --force")
    assert err is None
    assert force is True
    assert sid == _SIGNAL_FAILED


def test_resolve_status_quant_core_only(ledger_db: DuckClaw) -> None:
    st, src = _resolve_trade_signal_status(ledger_db, _SIGNAL_QUANT_ONLY)
    assert st == "FAILED"
    assert src == "quant_core"


def test_cancel_failed_signal(ledger_db: DuckClaw) -> None:
    out = execute_cancel_signal(ledger_db, "chat-1", _SIGNAL_FAILED, tenant_id="default")
    assert "cancelada" in out.lower()
    assert _query_status(ledger_db, _SIGNAL_FAILED, "finance_worker") == "CANCELLED"
    assert _query_status(ledger_db, _SIGNAL_FAILED, "quant_core") == "CANCELLED"


def test_cancel_quant_core_only_failed(ledger_db: DuckClaw) -> None:
    out = execute_cancel_signal(ledger_db, "chat-1", _SIGNAL_QUANT_ONLY, tenant_id="default")
    assert "cancelada" in out.lower()
    assert _query_status(ledger_db, _SIGNAL_QUANT_ONLY, "quant_core") == "CANCELLED"


def test_reject_executed_without_force(ledger_db: DuckClaw) -> None:
    out = execute_cancel_signal(ledger_db, "chat-1", _SIGNAL_EXECUTED, tenant_id="default")
    assert "no se puede cancelar" in out.lower()
    assert _query_status(ledger_db, _SIGNAL_EXECUTED, "finance_worker") == "EXECUTED"


def test_force_cancel_expired(ledger_db: DuckClaw) -> None:
    out = execute_cancel_signal(
        ledger_db, "chat-1", f"{_SIGNAL_EXPIRED} --force", tenant_id="default"
    )
    assert "cancelada" in out.lower()
    assert _query_status(ledger_db, _SIGNAL_EXPIRED, "finance_worker") == "CANCELLED"
    assert _query_status(ledger_db, _SIGNAL_EXPIRED, "quant_core") == "CANCELLED"


def test_force_rejects_executed(ledger_db: DuckClaw) -> None:
    out = execute_cancel_signal(
        ledger_db, "chat-1", f"{_SIGNAL_EXECUTED} --force", tenant_id="default"
    )
    assert "executed" in out.lower()
    assert _query_status(ledger_db, _SIGNAL_EXECUTED, "finance_worker") == "EXECUTED"


def test_reject_expired_without_force(ledger_db: DuckClaw) -> None:
    out = execute_cancel_signal(ledger_db, "chat-1", _SIGNAL_EXPIRED, tenant_id="default")
    assert "no se puede cancelar" in out.lower()
    assert "expired" in out.lower()
