"""Tests PUT /playground/knowledge-scope (DB-writer, no RW gateway handle)."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

_HEADERS = {"X-Admin-Key": "test-admin-key"}


@pytest.fixture
def gateway_with_runtime_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from duckclaw.schema_migrations import run_pending_migrations

    dbf = tmp_path / "gw.duckdb"
    con = duckdb.connect(str(dbf))
    try:
        run_pending_migrations(con)
    finally:
        con.close()
    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", str(dbf))
    return dbf


def _apply_typed_command_inline(command: object, *, db_path: str, user_id: str) -> str:
    from duckclaw.write_command_handlers import dispatch_command

    _ = user_id
    con = duckdb.connect(db_path, read_only=False)
    try:
        dispatch_command(con, command.model_dump())
    finally:
        con.close()
    return command.task_id


def test_playground_set_knowledge_scope_persists_via_db_writer(
    admin_client: TestClient, gateway_with_runtime_settings: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("duckclaw.db_write_queue.enqueue_typed_command", _apply_typed_command_inline)
    monkeypatch.setattr("duckclaw.db_write_queue.poll_task_status_sync", lambda *args, **kwargs: None)
    r = admin_client.put(
        "/api/v1/admin/playground/knowledge-scope",
        headers=_HEADERS,
        json={"chat_id": "admin-conv-rag", "knowledge_scope": "platform"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["task_id"]
    assert data["knowledge_scope"] == "platform"

    con = duckdb.connect(str(gateway_with_runtime_settings), read_only=True)
    try:
        row = con.execute(
            "SELECT value_text FROM main.admin_runtime_settings "
            "WHERE actor_email = 'chat:admin-conv-rag' AND domain = 'runtime.session' "
            "AND key = 'knowledge_scope'"
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] == "platform"
