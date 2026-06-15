"""Regresión: override LLM del hub (admin) gana sobre vault separado."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from duckclaw.admin_runtime_settings import upsert_runtime_setting


def _init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path), read_only=False)
    con.execute("SELECT 1")
    con.close()


def _set_llm_triplet(db, chat_id: str, provider: str, model: str, base_url: str) -> None:
    for key, value in {
        "llm_provider": provider,
        "llm_model": model,
        "llm_base_url": base_url,
    }.items():
        upsert_runtime_setting(
            db,
            tenant_id="default",
            actor_email=f"chat:{chat_id}",
            domain="runtime.session",
            key=key,
            value_text=value,
        )


def test_hub_llm_override_wins_over_vault_separate(tmp_path: Path) -> None:
    hub = tmp_path / "hub.duckdb"
    vault = tmp_path / "vault.duckdb"
    _init_db(hub)
    _init_db(vault)

    chat_id = "admin-conv-test-hub-vault"
    from duckclaw import DuckClaw
    from duckclaw.graphs.graph_server import _resolve_llm_triplet_for_graph_invoke

    hub_db = DuckClaw(str(hub), read_only=False, engine="python")
    vault_db = DuckClaw(str(vault), read_only=False, engine="python")
    try:
        _set_llm_triplet(hub_db, chat_id, "deepseek", "deepseek-chat", "https://api.deepseek.com/v1")
        _set_llm_triplet(
            vault_db,
            chat_id,
            "openrouter",
            "anthropic/claude-sonnet-4-5",
            "https://openrouter.ai/api/v1",
        )
    finally:
        hub_db.close()
        vault_db.close()

    hub_ro = DuckClaw(str(hub), read_only=True, engine="python")
    try:
        trip, source = _resolve_llm_triplet_for_graph_invoke(
            hub_ro,
            chat_id,
            str(vault),
            same_file=False,
        )
    finally:
        hub_ro.close()

    assert source == "hub_over_vault"
    assert trip is not None
    assert trip[0] == "deepseek"
    assert trip[1] == "deepseek-chat"


def test_vault_llm_used_when_hub_has_no_chat_override(tmp_path: Path) -> None:
    hub = tmp_path / "hub2.duckdb"
    vault = tmp_path / "vault2.duckdb"
    _init_db(hub)
    _init_db(vault)

    chat_id = "admin-conv-vault-only"
    from duckclaw import DuckClaw
    from duckclaw.graphs.graph_server import _resolve_llm_triplet_for_graph_invoke

    vault_db = DuckClaw(str(vault), read_only=False, engine="python")
    try:
        _set_llm_triplet(
            vault_db,
            chat_id,
            "groq",
            "llama-3.3-70b-versatile",
            "https://api.groq.com/openai/v1",
        )
    finally:
        vault_db.close()

    hub_ro = DuckClaw(str(hub), read_only=True, engine="python")
    try:
        trip, source = _resolve_llm_triplet_for_graph_invoke(
            hub_ro,
            chat_id,
            str(vault),
            same_file=False,
        )
    finally:
        hub_ro.close()

    assert source == "vault_separate"
    assert trip is not None
    assert trip[0] == "groq"
