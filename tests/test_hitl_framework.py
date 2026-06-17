"""Tests for transversal HITL services in DuckClaw core."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from duckclaw.hitl.code_decision_service import fetch_code_decision_row, reject_code_decision
from duckclaw.hitl.uncertainty_service import list_pending_uncertainty_events, resolve_uncertainty_event
from duckclaw.write_command_handlers import dispatch_command


class _DbShim:
    def __init__(self, path: str) -> None:
        self._path = path
        self._read_only = True
        self._con = duckdb.connect(path, read_only=True)

    def query(self, sql: str, params: tuple = ()):
        return self._con.execute(sql, params).fetchdf().to_dict(orient="records")

    def close(self) -> None:
        self._con.close()


@pytest.fixture()
def hitl_vault(tmp_path: Path) -> str:
    db_path = tmp_path / "hitl.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            CREATE TABLE main.code_decisions (
                id VARCHAR PRIMARY KEY,
                repo VARCHAR,
                file_path VARCHAR,
                branch_name VARCHAR,
                proposed_change TEXT,
                decision_type VARCHAR,
                title VARCHAR,
                rationale TEXT,
                status VARCHAR,
                pr_url VARCHAR,
                pr_number BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                resolved_by VARCHAR
            )
            """
        )
        con.execute(
            """
            INSERT INTO main.code_decisions
              (id, repo, file_path, branch_name, proposed_change, title, rationale, status)
            VALUES
              ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'duckclaw', 'README.md', 'feat/hitl', 'change', 'title', 'why', 'PENDING_HITL')
            """
        )
        con.execute(
            """
            CREATE TABLE main.agent_uncertainty_log (
                id VARCHAR PRIMARY KEY,
                session_uid VARCHAR,
                worker_id VARCHAR,
                trigger_context VARCHAR,
                confidence_score DOUBLE,
                description TEXT,
                proposed_questions JSON,
                status VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                resolved_by VARCHAR
            )
            """
        )
        con.execute(
            """
            INSERT INTO main.agent_uncertainty_log
              (id, session_uid, worker_id, trigger_context, confidence_score, description, status)
            VALUES
              ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'sess-1', 'ui-designer', 'missing_tool', 0.4, 'need skill', 'PENDING_HITL')
            """
        )
    finally:
        con.close()
    return str(db_path)


def test_fetch_code_decision_row_reads_main_table(hitl_vault: str) -> None:
    db = _DbShim(hitl_vault)
    try:
        row = fetch_code_decision_row(db, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        assert row is not None
        assert row["status"] == "PENDING_HITL"
    finally:
        db.close()


def test_list_pending_uncertainty_events(hitl_vault: str) -> None:
    db = _DbShim(hitl_vault)
    try:
        rows = list_pending_uncertainty_events(db, limit=5)
        assert len(rows) == 1
        assert rows[0]["trigger_context"] == "missing_tool"
    finally:
        db.close()


class _RwDbShim:
    def __init__(self, path: str) -> None:
        self._path = path
        self._read_only = False
        self._con = duckdb.connect(path)

    def query(self, sql: str, params: tuple = ()):
        return self._con.execute(sql, params).fetchdf().to_dict(orient="records")

    def execute(self, sql: str, params: list | tuple | None = None):
        if params is None:
            return self._con.execute(sql)
        return self._con.execute(sql, params)

    def close(self) -> None:
        self._con.close()


def test_resolve_uncertainty_event_updates_status(hitl_vault: str) -> None:
    db = _RwDbShim(hitl_vault)
    try:
        result = resolve_uncertainty_event(
            db,
            event_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            tenant_id="default",
            user_id="operator",
        )
        assert result.get("status") == "RESOLVED"
    finally:
        db.close()

    con = duckdb.connect(hitl_vault)
    try:
        row = con.execute(
            "SELECT status FROM main.agent_uncertainty_log WHERE id = ?",
            ["bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"],
        ).fetchone()
        assert row is not None
        assert row[0] == "RESOLVED"
    finally:
        con.close()


def test_reject_code_decision_updates_status(hitl_vault: str) -> None:
    db = _RwDbShim(hitl_vault)
    try:
        result = reject_code_decision(
            db,
            decision_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            tenant_id="default",
            user_id="operator",
            rationale="no",
        )
        assert result.get("status") == "REJECTED"
    finally:
        db.close()

    db_ro = _DbShim(hitl_vault)
    try:
        row = fetch_code_decision_row(db_ro, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        assert row is not None
        assert row["status"] == "REJECTED"
    finally:
        db_ro.close()
