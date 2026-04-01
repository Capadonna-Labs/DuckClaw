"""Convención TELEGRAM_<ID_AGENT>_TOKEN y aliases legados."""

from __future__ import annotations

import pytest

from duckclaw.integrations.telegram import telegram_agent_token as m


def test_telegram_agent_token_env_name() -> None:
    assert m.telegram_agent_token_env_name("bi_analyst") == "TELEGRAM_BI_ANALYST_TOKEN"
    assert m.telegram_agent_token_env_name("finanz") == "TELEGRAM_FINANZ_TOKEN"
    assert m.telegram_agent_token_env_name("LeilaAssistant") == "TELEGRAM_LEILAASSISTANT_TOKEN"


def test_resolve_prefers_standard_over_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BI_ANALYST_TOKEN", "new-tok")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_BI_ANALYST", "old-tok")
    assert m.resolve_telegram_token_for_worker_id("bi_analyst") == "new-tok"


def test_resolve_legacy_bi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BI_ANALYST_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_BI_ANALYST", "legacy-bi")
    assert m.resolve_telegram_token_for_worker_id("bi_analyst") == "legacy-bi"


def test_resolve_finanz_fallback_bot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_FINANZ_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "only-generic")
    assert m.resolve_telegram_token_for_worker_id("finanz") == "only-generic"


def test_resolve_flat_env_bi_analyst_alias() -> None:
    kv = {"TELEGRAM_BI_ANALYST_TOKEN": "x"}
    assert m.resolve_telegram_token_from_flat_env(kv, "BI-Analyst") == "x"