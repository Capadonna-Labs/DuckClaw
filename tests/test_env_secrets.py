"""Secretos solo en .env — no persistir en ecosystem PM2."""

from __future__ import annotations

from duckclaw.env_secrets import is_secret_env_key, strip_secrets_from_env


def test_is_secret_env_key() -> None:
    assert is_secret_env_key("DEEPSEEK_API_KEY")
    assert is_secret_env_key("TELEGRAM_BOT_TOKEN")
    assert is_secret_env_key("TELEGRAM_MARCO_ASSISTANT_TOKEN")
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
