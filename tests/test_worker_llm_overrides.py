"""Per-worker LLM model: tenant rows win over global; empty = inherit the chat's model."""

from __future__ import annotations

from pathlib import Path

import duckclaw
from duckclaw.admin_runtime_settings import ensure_admin_runtime_settings_table
from duckclaw.worker_llm_overrides import apply_worker_llm_override, list_worker_llm_models


def _db(tmp_path: Path):
    db = duckclaw.DuckClaw(str(tmp_path / "hub.duckdb"))
    ensure_admin_runtime_settings_table(db)
    for tenant, key, value in (
        ("global", "data_analyst", "deepseek/deepseek-v4.1-flash"),
        ("t1", "data_analyst", "anthropic/claude-haiku-5.5"),
        ("t1", "research-agent", ""),  # explicit inherit
    ):
        db.execute(
            "INSERT INTO main.admin_runtime_settings (setting_id, tenant_id, actor_email, domain, key, "
            f"value_text, value_kind, active) VALUES ('{tenant}-{key}', '{tenant}', '', 'worker_llm', "
            f"'{key}', '{value}', 'string', true)"
        )
    return db


def test_tenant_wins_and_empty_inherits(tmp_path: Path) -> None:
    db = _db(tmp_path)
    assert list_worker_llm_models(db, tenant_id="t1") == {"data_analyst": "anthropic/claude-haiku-5.5"}
    assert list_worker_llm_models(db, tenant_id="t2") == {"data_analyst": "deepseek/deepseek-v4.1-flash"}


def test_apply_override_drops_chat_llm(tmp_path: Path) -> None:
    db = _db(tmp_path)
    chat_llm = object()
    llm, prov, model, base = apply_worker_llm_override(
        db, tenant_id="t1", worker_id="data_analyst", llm=chat_llm,
        llm_provider="openrouter", llm_model="deepseek/deepseek-v4.1-flash", llm_base_url="x",
    )
    assert llm is None and prov == "openrouter" and model == "anthropic/claude-haiku-5.5"
    # No override (or inherit): the chat's llm and triplet pass through untouched.
    out = apply_worker_llm_override(
        db, tenant_id="t1", worker_id="Research-Agent", llm=chat_llm,
        llm_provider="openrouter", llm_model="m", llm_base_url="x",
    )
    assert out == (chat_llm, "openrouter", "m", "x")
