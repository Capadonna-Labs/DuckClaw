"""Borrador de configuración (spec — persistencia solo en Review salvo Quick Save)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SovereignDraft(BaseModel):
    """Valores recogidos en la sesión; se materializan en disco al confirmar Review."""

    # Audit
    detected_os: str = ""
    is_apple_silicon: bool = False

    # Core
    redis_url: str = Field(default="redis://localhost:6379/0", description="Canal de comunicación")
    duckdb_vault_path: str = Field(default="db/sovereign_memory.duckdb", description="Bóveda de memoria")
    duckdb_shared_path: str = Field(default="", description="BD compartida opcional (ej. BI)")

    # Identity
    tenant_id: str = "default"
    gateway_pm2_name: str = "DuckClaw-Gateway"
    default_worker_id: str = "BI-Analyst"

    # Connectivity
    telegram_bot_token: str = ""
    telegram_bot_token_masked: bool = False
    telegram_webhook_secret: str = ""
    telegram_webhook_secret_masked: bool = False
    duckclaw_tailscale_auth_key: str = ""
    tailscale_key_masked: bool = False
    enable_telegram_mcp: bool = True

    # Orchestration
    orchestration: Literal["pm2", "docker"] = "pm2"
    gateway_port: int = 8282
    redis_local_managed: bool = False
    generate_docker_compose: bool = True

    # LLM defaults (minimal)
    llm_provider: str = "deepseek"
    llm_model: str = "deepseek-chat"
    llm_base_url: str = "https://api.deepseek.com/"

    # Wizard legacy keys (wizard_config.json)
    channel: str = "telegram"
    bot_mode: str = "langgraph"
    mode: str = "polling"

    model_config = {"extra": "ignore"}
