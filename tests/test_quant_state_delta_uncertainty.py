"""Tests db-writer UNCERTAINTY_EVENT_LOGGED / UNCERTAINTY_RESOLVED."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import pytest

_REPO = Path(__file__).resolve().parents[1]
_GW = _REPO / "services" / "db-writer"
if str(_GW) not in sys.path:
    sys.path.insert(0, str(_GW))


def test_uncertainty_logged_and_resolved(tmp_path: Path) -> None:
    from quant_state_delta_handler import _apply_delta, _ensure_quant_ledger_schema
    from models.quant_state_delta import QuantStateDelta

    db_path = tmp_path / "quant.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        _ensure_quant_ledger_schema(con, str(db_path))
        con.execute(
            """
            INSERT INTO quant_core.trading_sessions
              (id, mode, tickers, session_uid, status)
            VALUES ('active', 'paper', 'SPY', 'sess-abc', 'ACTIVE')
            """
        )
    finally:
        con.close()

    event_id = "11111111-1111-4111-8111-111111111111"
    logged = QuantStateDelta(
        tenant_id="default",
        user_id="default",
        target_db_path=str(db_path),
        delta_type="UNCERTAINTY_EVENT_LOGGED",
        mutation={
            "id": event_id,
            "session_uid": "sess-abc",
            "worker_id": "quant_trader",
            "trigger_context": "missing_tool",
            "confidence_score": 0.5,
            "description": "test block",
            "proposed_questions": ["¿Qué skill falta?"],
            "status": "PENDING_HITL",
        },
    )
    con = duckdb.connect(str(db_path))
    try:
        _apply_delta(con, logged)
        row = con.execute(
            "SELECT status FROM quant_core.trading_sessions WHERE id='active'"
        ).fetchone()
        assert row is not None
        assert row[0] == "UNCERTAIN"
        pending = con.execute(
            "SELECT status FROM quant_core.agent_uncertainty_log WHERE id=?",
            [event_id],
        ).fetchone()
        assert pending is not None
        assert pending[0] == "PENDING_HITL"
    finally:
        con.close()

    resolved = QuantStateDelta(
        tenant_id="default",
        user_id="default",
        target_db_path=str(db_path),
        delta_type="UNCERTAINTY_RESOLVED",
        mutation={"id": event_id, "session_uid": "sess-abc"},
    )
    con = duckdb.connect(str(db_path))
    try:
        _apply_delta(con, resolved)
        st = con.execute(
            "SELECT status FROM quant_core.agent_uncertainty_log WHERE id=?",
            [event_id],
        ).fetchone()
        assert st is not None
        assert st[0] == "RESOLVED"
        sess = con.execute(
            "SELECT status FROM quant_core.trading_sessions WHERE id='active'"
        ).fetchone()
        assert sess is not None
        assert sess[0] == "ACTIVE"
    finally:
        con.close()
