"""Tests for /summarize manual context fold command."""

from __future__ import annotations

from types import SimpleNamespace

import duckdb
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from duckclaw.commands.chat_state import set_chat_state
from duckclaw.commands.context_summarize import (
    execute_summarize,
    load_vault_conversation_history,
    run_manual_context_fold,
)
from duckclaw.workers.context_monitor import apply_context_monitor_state


class _FakeSummaryLLM:
    def invoke(self, messages):  # noqa: ANN001
        return SimpleNamespace(content="Resumen manual generado")


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


def _ensure_tables(vault_path: str) -> None:
    con = duckdb.connect(vault_path)
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS agent_config ("
            "key VARCHAR PRIMARY KEY, value TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS api_conversation ("
            "session_id VARCHAR NOT NULL, worker_id VARCHAR NOT NULL, role VARCHAR NOT NULL, "
            "content TEXT, author_type VARCHAR DEFAULT 'AI', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
    finally:
        con.close()


def test_apply_context_monitor_force_prune_folds_short_thread() -> None:
    llm = _FakeSummaryLLM()
    state = {
        "messages": [
            SystemMessage(content="Sistema"),
            HumanMessage(content="mensaje uno"),
            HumanMessage(content="mensaje dos"),
            AIMessage(content="respuesta"),
        ],
    }
    out = apply_context_monitor_state(
        state,
        pruning_config={
            "enabled": True,
            "max_messages": 10_000,
            "max_estimated_tokens": 4_000_000,
            "keep_last_messages": 1,
            "tool_content_max_chars": 8000,
        },
        prompt_base="Sistema",
        llm_summary=llm,
        force_prune=True,
    )
    assert out["analytical_summary"] == "Resumen manual generado"
    assert len(out["messages"]) == 2


def test_load_vault_conversation_history_from_api(tmp_path) -> None:
    vault = tmp_path / "vault.duckdb"
    _ensure_tables(str(vault))
    con = duckdb.connect(str(vault))
    try:
        con.execute(
            "INSERT INTO api_conversation (session_id, worker_id, role, content) "
            "VALUES ('chat-1', 'default', 'user', 'hola')"
        )
        con.execute(
            "INSERT INTO api_conversation (session_id, worker_id, role, content) "
            "VALUES ('chat-1', 'default', 'assistant', 'hola de vuelta')"
        )
    finally:
        con.close()
    db = _RwVault(str(vault))
    hist = load_vault_conversation_history(db, "chat-1")
    assert len(hist) == 2
    assert hist[0]["role"] == "user"
    assert hist[1]["role"] == "assistant"


def test_run_manual_context_fold_uses_explicit_history(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_CONTEXT_PRUNE_ENABLED", raising=False)
    monkeypatch.setenv("DUCKCLAW_CONTEXT_FOLD_PERSIST", "0")
    vault = tmp_path / "vault.duckdb"
    _ensure_tables(str(vault))
    db = _RwVault(str(vault))
    set_chat_state(db, "chat-fold-1", "worker_id", "default")

    monkeypatch.setattr(
        "duckclaw.commands.context_summarize.build_summary_llm",
        lambda *args, **kwargs: _FakeSummaryLLM(),
    )
    monkeypatch.setattr(
        "duckclaw.integrations.llm_providers.build_llm",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        "duckclaw.commands.context_summarize._effective_llm_triplet_for_chat_ui",
        lambda *_a, **_k: ("openrouter", "test/model", "https://openrouter.ai/api/v1"),
    )
    monkeypatch.setattr(
        "duckclaw.commands.context_summarize._catalog_db_for_manifest",
        lambda: None,
    )

    history = [
        {"role": "user", "content": "primera pregunta larga " + ("x" * 200)},
        {"role": "assistant", "content": "primera respuesta"},
        {"role": "user", "content": "segunda pregunta"},
    ]
    summary, err, meta = run_manual_context_fold(
        db,
        "chat-fold-1",
        tenant_id="default",
        worker_id="default",
        history=history,
    )
    assert err is None
    assert summary == "Resumen manual generado"
    assert meta.get("summary_for_vault") == "Resumen manual generado"
    assert isinstance(meta.get("context_estimated_tokens"), int)
    assert meta.get("context_estimated_tokens", 0) > 0


def test_execute_summarize_rejects_when_global_off(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_CONTEXT_PRUNE_ENABLED", "0")
    vault = tmp_path / "vault.duckdb"
    _ensure_tables(str(vault))
    db = _RwVault(str(vault))
    out = execute_summarize(db, "chat-fold-1", "", tenant_id="default")
    assert "desactivado globalmente" in out


def test_run_manual_context_fold_rejects_manager_without_explicit_worker(tmp_path, monkeypatch) -> None:
    """Sin worker_id explícito cae en manager y falla en catálogo tenant (regresión)."""
    monkeypatch.delenv("DUCKCLAW_CONTEXT_PRUNE_ENABLED", raising=False)
    vault = tmp_path / "vault.duckdb"
    _ensure_tables(str(vault))
    db = _RwVault(str(vault))
    history = [
        {"role": "user", "content": "uno"},
        {"role": "assistant", "content": "dos"},
    ]
    summary, err, meta = run_manual_context_fold(
        db,
        "chat-fold-1",
        tenant_id="user-tenant-x",
        history=history,
    )
    assert summary is None
    assert err is not None
    assert "manager" in err.lower() or "catalog" in err.lower() or "not found" in err.lower()


def test_execute_summarize_help_text(tmp_path) -> None:
    vault = tmp_path / "vault.duckdb"
    _ensure_tables(str(vault))
    db = _RwVault(str(vault))
    out = execute_summarize(db, "chat-fold-1", "help", tenant_id="default")
    assert "/summarize" in out
    assert "context monitor" in out.lower()
