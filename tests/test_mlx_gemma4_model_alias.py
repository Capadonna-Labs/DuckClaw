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
    monkeypatch.setenv("MLX_MODEL_PATH", "/data/models/Slayer-8B-V1")
    assert mlx_openai_compatible_model_name("gemma4") == MLX_GEMMA4_DEFAULT_REPO_ID
    assert mlx_openai_compatible_model_name("Gemma-4") == MLX_GEMMA4_DEFAULT_REPO_ID


def test_mlx_short_name_non_gemma_still_uses_mlx_model_path(monkeypatch) -> None:
    monkeypatch.delenv("MLX_GEMMA4_MODEL_PATH", raising=False)
    monkeypatch.setenv("MLX_MODEL_PATH", "/data/models/Slayer-8B-V1")
    assert mlx_openai_compatible_model_name("Slayer-8B") == "/data/models/Slayer-8B-V1"
