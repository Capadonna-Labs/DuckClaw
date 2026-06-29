"""Secretos solo en .env — no persistir en ecosystem PM2."""

from __future__ import annotations

from duckclaw.env_secrets import (
    apply_dotenv_overrides_to_os_environ,
    is_secret_env_key,
    strip_secrets_from_env,
)


def test_is_secret_env_key() -> None:
    assert is_secret_env_key("DEEPSEEK_API_KEY")
    assert is_secret_env_key("OPENROUTER_API_KEY")
    assert is_secret_env_key("TELEGRAM_BOT_TOKEN")
    assert is_secret_env_key("TELEGRAM_EXAMPLE_ASSISTANT_TOKEN")
    assert is_secret_env_key("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES")
    assert not is_secret_env_key("DUCKCLAW_LLM_PROVIDER")
    assert not is_secret_env_key("DUCKDB_PATH")


def test_strip_secrets_from_env() -> None:
    raw = {
        "DUCKCLAW_LLM_PROVIDER": "deepseek",
        "DEEPSEEK_API_KEY": "sk-test",
        "TELEGRAM_BOT_TOKEN": "123:ABC",
        "DUCKDB_PATH": "db/x.duckdb",
    }
    out = strip_secrets_from_env(raw)
    assert out == {"DUCKCLAW_LLM_PROVIDER": "deepseek", "DUCKDB_PATH": "db/x.duckdb"}


def test_dotenv_override_replaces_stale_empty_openrouter_key(monkeypatch) -> None:
    """PM2 puede dejar OPENROUTER_API_KEY=''; .env debe ganar (DOTENV_OVERRIDE_KEYS)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    apply_dotenv_overrides_to_os_environ(
        {"OPENROUTER_API_KEY": "sk-or-from-dotenv", "DEEPSEEK_API_KEY": ""}
    )
    import os

    assert os.environ["OPENROUTER_API_KEY"] == "sk-or-from-dotenv"
    assert os.environ["DEEPSEEK_API_KEY"] == ""
