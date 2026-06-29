"""Round-trip y forget para context_fold_summary en bóveda DuckDB."""

from __future__ import annotations

import json
from types import SimpleNamespace

import duckdb

from duckclaw.commands.chat_state import forget_chat_state, get_chat_state, set_chat_state
from duckclaw.commands.context_fold_store import (
    CONTEXT_FOLD_KEY,
    load_context_fold_summary,
    save_context_fold_summary,
)


class _RwVault:
    def __init__(self, path: str) -> None:
        self._path = path
        self._read_only = False

    def execute(self, sql: str, params=None):
        con = duckdb.connect(self._path)
        try:
            if params is not None:
                return con.execute(sql, params)
            return con.execute(sql)
        finally:
            con.close()

    def query(self, sql: str, params=None) -> str:
        import json

        con = duckdb.connect(self._path, read_only=True)
        try:
            if params is not None:
                result = con.execute(sql, params)
            else:
                result = con.execute(sql)
            rows = result.fetchall()
            names = [d[0] for d in result.description]
            out = [dict(zip(names, ("" if v is None else str(v) for v in row))) for row in rows]
            return json.dumps(out, ensure_ascii=False)
        finally:
            con.close()


def _ensure_agent_config_table(vault_path: str) -> None:
    con = duckdb.connect(vault_path)
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS agent_config ("
            "key VARCHAR PRIMARY KEY, value TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
    finally:
        con.close()


def test_load_context_fold_summary_from_vault(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_CONTEXT_FOLD_PERSIST", "1")
    vault = tmp_path / "vault.duckdb"
    _ensure_agent_config_table(str(vault))
    db = _RwVault(str(vault))
    set_chat_state(db, "chat-fold-1", CONTEXT_FOLD_KEY, "resumen previo")

    assert load_context_fold_summary(str(vault), "chat-fold-1") == "resumen previo"


def test_save_context_fold_summary_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_CONTEXT_FOLD_PERSIST", "1")
    vault = tmp_path / "vault.duckdb"
    _ensure_agent_config_table(str(vault))

    def _fake_enqueue(command, **kwargs):
        con = duckdb.connect(str(vault))
        try:
            from duckclaw.write_command_handlers import dispatch_command

            dispatch_command(con, json.loads(command.to_redis_payload()))
        finally:
            con.close()
        return "task-fold-1"

    monkeypatch.setattr(
        "duckclaw.commands.chat_state.db_write_queue.enqueue_typed_command",
        _fake_enqueue,
    )
    monkeypatch.setattr(
        "duckclaw.commands.chat_state.db_write_queue.poll_task_status_sync",
        lambda *_a, **_k: SimpleNamespace(status="success", detail=""),
    )

    ok = save_context_fold_summary(str(vault), "chat-fold-1", "nuevo fold", tenant_id="default")
    assert ok is True
    assert load_context_fold_summary(str(vault), "chat-fold-1") == "nuevo fold"


def test_forget_chat_state_removes_context_fold_summary(tmp_path) -> None:
    vault = tmp_path / "vault.duckdb"
    _ensure_agent_config_table(str(vault))
    db = _RwVault(str(vault))
    set_chat_state(db, "chat-fold-1", CONTEXT_FOLD_KEY, "borrar")
    set_chat_state(db, "chat-fold-1", "last_audit", "{}")

    forget_chat_state(db, "chat-fold-1")

    assert get_chat_state(db, "chat-fold-1", CONTEXT_FOLD_KEY) == ""
    assert get_chat_state(db, "chat-fold-1", "last_audit") == ""


def test_context_fold_persist_disabled_skips_io(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_CONTEXT_FOLD_PERSIST", "0")
    vault = tmp_path / "vault.duckdb"
    _ensure_agent_config_table(str(vault))
    db = _RwVault(str(vault))
    set_chat_state(db, "chat-fold-1", CONTEXT_FOLD_KEY, "oculto")

    assert load_context_fold_summary(str(vault), "chat-fold-1") == ""
    assert save_context_fold_summary(str(vault), "chat-fold-1", "nuevo") is False
