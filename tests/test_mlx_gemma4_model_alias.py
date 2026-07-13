"""mlx_openai_compatible_model_name: alias gemma4 / gemma-4 para ChatOpenAI → mlx_lm.server."""

from duckclaw.integrations.llm_providers import (
    MLX_GEMMA4_DEFAULT_REPO_ID,
    mlx_openai_compatible_model_name,
)


def test_mlx_gemma4_alias_uses_env_path(monkeypatch) -> None:
    monkeypatch.setenv("MLX_GEMMA4_MODEL_PATH", "/data/models/gemma4-mlx")
    monkeypatch.delenv("MLX_MODEL_PATH", raising=False)
    monkeypatch.delenv("MLX_MODEL_ID", raising=False)
    assert mlx_openai_compatible_model_name("gemma4") == "/data/models/gemma4-mlx"
    assert mlx_openai_compatible_model_name("gemma-4") == "/data/models/gemma4-mlx"


def test_mlx_gemma4_alias_default_repo_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv("MLX_GEMMA4_MODEL_PATH", raising=False)
    monkeypatch.setenv("MLX_MODEL_PATH", "/data/models/custom-model-v1")
    assert mlx_openai_compatible_model_name("gemma4") == MLX_GEMMA4_DEFAULT_REPO_ID
    assert mlx_openai_compatible_model_name("Gemma-4") == MLX_GEMMA4_DEFAULT_REPO_ID


def test_mlx_gemma4_alias_follows_mlx_model_path_when_gemma(monkeypatch) -> None:
    """Evita desalinear gateway (alias gemma4) y servidor MLX precargado con la misma ruta."""
    monkeypatch.delenv("MLX_GEMMA4_MODEL_PATH", raising=False)
    monkeypatch.setenv("MLX_MODEL_PATH", "/Users/me/Desktop/models/gemma4-e4b")
    assert mlx_openai_compatible_model_name("gemma4") == "/Users/me/Desktop/models/gemma4-e4b"


def test_mlx_rejects_openrouter_slug(monkeypatch) -> None:
    monkeypatch.setenv("MLX_MODEL_ID", "mlx-community/Qwen2.5-Coder-3B-Instruct-4bit")
    assert (
        mlx_openai_compatible_model_name("z-ai/glm-5.2")
        == "mlx-community/Qwen2.5-Coder-3B-Instruct-4bit"
    )
    assert mlx_openai_compatible_model_name("mlx-community/Llama-3.2-3B-Instruct-4bit") == (
        "mlx-community/Llama-3.2-3B-Instruct-4bit"
    )


def test_mlx_base_url_uses_host_env(monkeypatch) -> None:
    from duckclaw.integrations.llm_providers import mlx_openai_compatible_base_url

    monkeypatch.setenv("DUCKCLAW_MLX_HOST", "100.99.72.63")
    monkeypatch.setenv("MLX_PORT", "8080")
    assert mlx_openai_compatible_base_url() == "http://100.99.72.63:8080/v1"


def test_mlx_base_url_explicit_override(monkeypatch) -> None:
    from duckclaw.integrations.llm_providers import mlx_openai_compatible_base_url

    monkeypatch.setenv("DUCKCLAW_MLX_BASE_URL", "http://mini.local:9090/v1")
    monkeypatch.setenv("DUCKCLAW_MLX_HOST", "ignored")
    assert mlx_openai_compatible_base_url() == "http://mini.local:9090/v1"


def test_mlx_short_name_non_gemma_still_uses_mlx_model_path(monkeypatch) -> None:
    monkeypatch.delenv("MLX_GEMMA4_MODEL_PATH", raising=False)
    monkeypatch.setenv("MLX_MODEL_PATH", "/data/models/custom-model-v1")
    assert mlx_openai_compatible_model_name("custom-model") == "/data/models/custom-model-v1"
