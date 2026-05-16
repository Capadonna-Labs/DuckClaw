from __future__ import annotations

import pytest

from duckclaw.integrations.llm_providers import build_llm, infer_provider_from_openai_compatible_llm


def test_build_llm_gemini_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        build_llm("gemini", "gemini-2.0-flash", "", prefer_env_provider=False)


def test_build_llm_gemini_builds_chat_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.delenv("DUCKCLAW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_MODEL", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_BASE_URL", raising=False)
    llm = build_llm("gemini", "gemini-2.0-flash", "", prefer_env_provider=False)
    assert llm is not None
    assert "google" in type(llm).__module__.lower()
    assert "gemini" in infer_provider_from_openai_compatible_llm(llm)
