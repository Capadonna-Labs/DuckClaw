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


def test_pm2_env_dict_prefers_worker_token_over_generic_bot_token() -> None:
    """Evita que JobHunter-Gateway use TELEGRAM_BOT_TOKEN de Finanz del bloque PM2 fusionado."""
    env = {
        "TELEGRAM_BOT_TOKEN": "finanz-bot-token",
        "TELEGRAM_JOB_HUNTER_TOKEN": "job-hunter-bot-token",
    }
    assert m.telegram_token_from_pm2_env_dict(env, "Job-Hunter") == "job-hunter-bot-token"


def test_pm2_env_dict_finanz_still_falls_back_to_generic_bot_token() -> None:
    env = {"TELEGRAM_BOT_TOKEN": "only-finanz"}
    assert m.telegram_token_from_pm2_env_dict(env, "finanz") == "only-finanz"