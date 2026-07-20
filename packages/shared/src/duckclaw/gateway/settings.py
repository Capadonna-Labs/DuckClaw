"""Centralized gateway settings with production fail-fast validation."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


class GatewaySettings(BaseSettings):
    PROJECT_NAME: str = "DuckClaw API Gateway"
    VERSION: str = "0.1.0"

    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("REDIS_URL", "DUCKCLAW_REDIS_URL"),
    )

    JWT_SECRET: str = "dev-secret-change-in-production"

    TELEGRAM_BOT_USERNAME: str = Field(
        default="",
        validation_alias=AliasChoices("TELEGRAM_BOT_USERNAME", "DUCKCLAW_TELEGRAM_BOT_USERNAME"),
    )

    DUCKCLAW_DEV_MODE: bool = Field(
        default=False,
        validation_alias="DUCKCLAW_DEV_MODE",
    )

    DUCKCLAW_ADMIN_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    DUCKCLAW_LLM_PROVIDER: str = Field(
        default="",
        validation_alias=AliasChoices("DUCKCLAW_LLM_PROVIDER", "LLM_PROVIDER"),
    )
    DUCKCLAW_LLM_BASE_URL: str = Field(
        default="",
        validation_alias=AliasChoices("DUCKCLAW_LLM_BASE_URL", "LLM_BASE_URL"),
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("DUCKCLAW_DEV_MODE", mode="before")
    @classmethod
    def _coerce_dev_mode(cls, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return _truthy(os.environ.get("DUCKCLAW_DEV_MODE"))
        if isinstance(value, str):
            return _truthy(value)
        return bool(value)

    def resolved_redis_url(self) -> str:
        explicit = (self.REDIS_URL or "").strip()
        if explicit and explicit != "redis://localhost:6379/0":
            return explicit
        try:
            from duckclaw.runtime_env import resolve_redis_url

            return resolve_redis_url()
        except Exception:
            return explicit or "redis://localhost:6379/0"

    def require_production_secrets(self) -> None:
        """Fail fast when running outside dev mode without required secrets."""
        if self.DUCKCLAW_DEV_MODE:
            return
        missing: list[str] = []
        if not (self.DUCKCLAW_ADMIN_API_KEY or "").strip():
            missing.append("DUCKCLAW_ADMIN_API_KEY")
        provider = (self.DUCKCLAW_LLM_PROVIDER or "").strip().lower()
        if provider in ("openrouter", "or") and not (self.OPENROUTER_API_KEY or "").strip():
            missing.append("OPENROUTER_API_KEY")
        if provider in ("mlx", "ollama", "local", "iotcorelabs") and not (
            self.DUCKCLAW_LLM_BASE_URL or ""
        ).strip():
            missing.append("DUCKCLAW_LLM_BASE_URL")
        if missing:
            raise RuntimeError(
                "Gateway startup blocked: missing required env "
                f"{', '.join(missing)}. Set DUCKCLAW_DEV_MODE=1 for local dev or "
                "define secrets in .env."
            )


@lru_cache(maxsize=1)
def get_gateway_settings() -> GatewaySettings:
    settings = GatewaySettings()
    if not (settings.REDIS_URL or "").strip() or settings.REDIS_URL == "redis://localhost:6379/0":
        object.__setattr__(settings, "REDIS_URL", settings.resolved_redis_url())
    return settings


def reset_gateway_settings_cache() -> None:
    get_gateway_settings.cache_clear()
