"""Convención TELEGRAM_<ID_AGENT>_TOKEN."""

from __future__ import annotations

import pytest

from duckclaw.integrations.telegram import telegram_agent_token as m


def test_telegram_agent_token_env_name() -> None:
    assert m.telegram_agent_token_env_name("demo_analyst") == "TELEGRAM_DEMO_ANALYST_TOKEN"
    assert m.telegram_agent_token_env_name("worker_a") == "TELEGRAM_WORKER_A_TOKEN"


def test_resolve_standard_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_DEMO_ANALYST_TOKEN", "new-tok")
    assert m.resolve_telegram_token_for_worker_id("demo_analyst") == "new-tok"


def test_resolve_unknown_worker_does_not_use_generic_bot_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_WORKER_A_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "only-generic")
    assert m.resolve_telegram_token_for_worker_id("worker_a") == ""


def test_resolve_flat_env_hyphen_alias() -> None:
    kv = {"TELEGRAM_DEMO_ANALYST_TOKEN": "x"}
    assert m.resolve_telegram_token_from_flat_env(kv, "Demo-Analyst") == "x"


def test_pm2_env_dict_prefers_worker_token_over_generic_bot_token() -> None:
    """Evita que un gateway dedicado use TELEGRAM_BOT_TOKEN de otro bloque PM2 fusionado."""
    env = {
        "TELEGRAM_BOT_TOKEN": "generic-bot-token",
        "TELEGRAM_RESEARCH_WORKER_TOKEN": "research-worker-bot-token",
    }
    assert m.telegram_token_from_pm2_env_dict(env, "research-worker") == "research-worker-bot-token"


def test_pm2_env_dict_falls_back_to_generic_bot_token() -> None:
    env = {"TELEGRAM_BOT_TOKEN": "only-generic"}
    assert m.telegram_token_from_pm2_env_dict(env, "worker_a") == "only-generic"


def test_telegram_worker_ids_match_folder_vs_manifest_id() -> None:
    """Rutas compactas toleran guiones, underscores y case."""
    assert m.telegram_worker_ids_match_for_compact_route("Worker-A", "worker_a")
    assert m.telegram_worker_ids_match_for_compact_route("worker_a", "Worker-A")
    assert not m.telegram_worker_ids_match_for_compact_route("worker_b", "Worker-A")