"""Regresión: proveedor groq y alias LLM_* → DUCKCLAW_LLM_* en build_llm."""

from __future__ import annotations

import pytest

from duckclaw.integrations.llm_providers import build_llm


def test_build_llm_groq_returns_chat_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_dummy")
    monkeypatch.delenv("DUCKCLAW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_MODEL", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_BASE_URL", raising=False)
    llm = build_llm("groq", "llama-3.3-70b-versatile", "")
    assert llm is not None
    assert getattr(llm, "model_name", None) == "llama-3.3-70b-versatile"


def test_build_llm_groq_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        build_llm("groq", "llama-3.3-70b-versatile", "")


def test_build_llm_groq_ignores_deepseek_base_url_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PM2 suele dejar DUCKCLAW_LLM_BASE_URL en DeepSeek; Groq no debe llamar a ese host."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_dummy")
    monkeypatch.setenv("DUCKCLAW_LLM_PROVIDER", "groq")
    monkeypatch.setenv("DUCKCLAW_LLM_BASE_URL", "https://api.deepseek.com/")
    monkeypatch.delenv("DUCKCLAW_LLM_MODEL", raising=False)
    llm = build_llm("groq", "llama-3.3-70b-versatile", "")
    assert llm is not None
    assert getattr(llm, "openai_api_base", None) == "https://api.groq.com/openai/v1"


def test_build_llm_legacy_llm_provider_env_used_when_duckclaw_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Solo LLM_PROVIDER=groq: build_llm debe usar groq aunque el caller pase otro default."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_dummy")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.delenv("DUCKCLAW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_MODEL", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_BASE_URL", raising=False)
    llm = build_llm("mlx", "", "")
    assert llm is not None
    assert getattr(llm, "model_name", None) == "llama-3.3-70b-versatile"


def test_build_llm_mlx_resolves_short_alias_to_mlx_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Alias tipo Slayer-8B (chat / LLM_MODEL) → ruta local MLX_MODEL_PATH para la API OpenAI-compat."""
    monkeypatch.setenv("MLX_MODEL_PATH", "/data/models/Slayer-8B-V1")
    monkeypatch.delenv("MLX_MODEL_ID", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    llm = build_llm(
        "mlx",
        "Slayer-8B",
        "http://127.0.0.1:8080/v1",
        prefer_env_provider=False,
    )
    assert llm is not None
    assert getattr(llm, "model_name", None) == "/data/models/Slayer-8B-V1"


def test_build_llm_mlx_keeps_hf_repo_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLX_MODEL_PATH", "/should/not/use/for/hf/id")
    monkeypatch.delenv("DUCKCLAW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    llm = build_llm(
        "mlx",
        "mlx-community/Llama-3.2-1B-Instruct",
        "http://127.0.0.1:8080/v1",
        prefer_env_provider=False,
    )
    assert getattr(llm, "model_name", None) == "mlx-community/Llama-3.2-1B-Instruct"


def test_build_llm_deepseek_normalizes_bare_deepseek_to_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    """/model model=deepseek es ambiguo (provider vs id); la API rechaza el id literal 'deepseek'."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk_test_dummy")
    monkeypatch.delenv("DUCKCLAW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    llm = build_llm("deepseek", "deepseek", "", prefer_env_provider=False)
    assert llm is not None
    assert getattr(llm, "model_name", None) == "deepseek-chat"


def test_build_llm_coerces_groq_provider_when_model_is_deepseek_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evita groq + model=deepseek-chat cuando el merge deja provider=env groq y modelo del chat."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk_test_dummy")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_dummy")
    monkeypatch.setenv("DUCKCLAW_LLM_PROVIDER", "groq")
    monkeypatch.delenv("DUCKCLAW_LLM_MODEL", raising=False)
    llm = build_llm("groq", "deepseek-chat", "https://api.groq.com/openai/v1", prefer_env_provider=True)
    assert llm is not None
    assert getattr(llm, "model_name", None) == "deepseek-chat"
    assert getattr(llm, "openai_api_base", None) == "https://api.deepseek.com/v1"


def test_build_llm_deepseek_ignores_groq_base_url_from_env_style_triplet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si la tripleta hereda DUCKCLAW_LLM_BASE_URL=Groq, no enviar deepseek-chat al host Groq (400 Model Not Exist)."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk_test_dummy")
    monkeypatch.delenv("DUCKCLAW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_MODEL", raising=False)
    monkeypatch.delenv("DUCKCLAW_LLM_BASE_URL", raising=False)
    llm = build_llm(
        "deepseek",
        "deepseek-chat",
        "https://api.groq.com/openai/v1",
        prefer_env_provider=False,
    )
    assert llm is not None
    assert getattr(llm, "model_name", None) == "deepseek-chat"
    assert getattr(llm, "openai_api_base", None) == "https://api.deepseek.com/v1"


def test_build_llm_mlx_keeps_absolute_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLX_MODEL_PATH", "/other")
    monkeypatch.delenv("DUCKCLAW_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    llm = build_llm(
        "mlx",
        "/Users/me/Slayer",
        "http://127.0.0.1:8080/v1",
        prefer_env_provider=False,
    )
    assert getattr(llm, "model_name", None) == "/Users/me/Slayer"
