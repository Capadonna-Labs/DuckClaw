"""Regresión: proveedor OpenRouter con app attribution headers."""

from __future__ import annotations

import pytest

from duckclaw.integrations.llm_providers import (
    OPENROUTER_ATTRIBUTION_HEADERS,
    build_llm,
    build_openrouter_llm,
)


def test_build_llm_openrouter_returns_chat_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test_dummy")
    monkeypatch.delenv("DUCKCLAW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_MODEL", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    llm = build_llm("openrouter", "", "", prefer_env_provider=False)
    assert llm is not None
    assert getattr(llm, "model_name", None) == "anthropic/claude-sonnet-4-5"


def test_build_llm_openrouter_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_PROVIDER", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        build_llm("openrouter", "", "", prefer_env_provider=False)


def test_build_llm_openrouter_ignores_deepseek_base_url_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test_dummy")
    monkeypatch.setenv("DUCKCLAW_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("DUCKCLAW_LLM_BASE_URL", "https://api.deepseek.com/")
    monkeypatch.delenv("DUCKCLAW_LLM_MODEL", raising=False)
    llm = build_llm("openrouter", "anthropic/claude-sonnet-4-5", "")
    assert llm is not None
    assert getattr(llm, "openai_api_base", None) == "https://openrouter.ai/api/v1"


def test_build_openrouter_llm_default_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test_dummy")
    llm = build_openrouter_llm()
    headers = getattr(llm, "default_headers", None) or {}
    assert headers.get("HTTP-Referer") == OPENROUTER_ATTRIBUTION_HEADERS["HTTP-Referer"]
    assert headers.get("X-OpenRouter-Title") == OPENROUTER_ATTRIBUTION_HEADERS["X-OpenRouter-Title"]


def test_build_llm_openrouter_alias_or(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test_dummy")
    monkeypatch.delenv("DUCKCLAW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_MODEL", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    llm = build_llm("or", "", "", prefer_env_provider=False)
    assert llm is not None
    assert getattr(llm, "openai_api_base", None) == "https://openrouter.ai/api/v1"


def test_build_llm_openrouter_alias_router(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test_dummy")
    monkeypatch.delenv("DUCKCLAW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    llm = build_llm("router", "", "", prefer_env_provider=False)
    assert llm is not None
    assert getattr(llm, "model_name", None) == "anthropic/claude-sonnet-4-5"


def test_build_llm_openrouter_explicit_model_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test_dummy")
    monkeypatch.delenv("DUCKCLAW_LLM_PROVIDER", raising=False)
    llm = build_llm(
        "openrouter",
        "google/gemini-2.5-pro",
        "",
        prefer_env_provider=False,
    )
    assert getattr(llm, "model_name", None) == "google/gemini-2.5-pro"
