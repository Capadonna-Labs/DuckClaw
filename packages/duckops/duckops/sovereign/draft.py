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
    duckdb_vault_path: str = Field(
        default="db/sovereign_memory.duckdb",
        description="Hub DuckDB (multiplex / DUCKDB_PATH); el wizard lo infiere del .env si hay rutas por agente",
    )
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
    #: Base HTTPS que llega a este gateway (túnel/proxy). Sin barra final. Para generar setWebhook al desplegar.
    telegram_webhook_public_base_url: str = ""
    #: Si el túnel se registró en PM2 (Quick Tunnel), nombre del proceso; solo informativo.
    cloudflared_pm2_process_name: str = ""
    #: El wizard ejecutó `tailscale funnel --bg --yes` hacia el puerto del gateway.
    tailscale_funnel_bg_via_wizard: bool = False
    duckclaw_tailscale_auth_key: str = ""
    tailscale_key_masked: bool = False
    enable_telegram_mcp: bool = True

    #: Telegram Guard: tu user_id numérico (quien ejecuta el wizard) → role admin al materializar.
    wizard_creator_telegram_user_id: str = ""
    #: Nombre para mostrar del admin creador (columna username en authorized_users; ej. Juan).
    wizard_creator_admin_display_name: str = ""
    #: IDs adicionales como admin, separados por coma (opcional).
    wizard_extra_admin_telegram_ids: str = ""

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
