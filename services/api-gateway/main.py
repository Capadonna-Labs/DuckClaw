# services/api-gateway/main.py
"""
DuckClaw API Gateway — Microservicio unificado.

Punto de entrada único para Telegram (webhook/long polling), clientes HTTP, Angular y escrituras a DuckDB.
Endpoints: /api/v1/agent/chat, /api/v1/db/write, homeostasis, system health.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

_REPO_ROOT_FOR_DB = Path(__file__).resolve().parent.parent.parent
os.environ.setdefault("DUCKCLAW_REPO_ROOT", str(_REPO_ROOT_FOR_DB))

from core.gateway_bootstrap import apply_gateway_bootstrap

apply_gateway_bootstrap()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.agent_chat import invoke_chat, resolve_chat_session_id, router as agent_chat_router
from core.agent_routes import effective_tenant_id, router as agent_routes_router
from core.chat_auth import authorize_or_reject
from core.chat_reply_format import clean_agent_response
from core.chat_visual_artifacts import (
    admin_visual_fields_from_invoke_result,
    persist_admin_fly_charts,
)
from core.db_read_route import router as db_read_router
from core.gateway_vault import dedicated_gateway_vault_db_path
from core.health import router as health_router
from core.homeostasis import router as homeostasis_router
from core.lifespan import lifespan
from core.middleware import register_gateway_middleware
from core.telegram_delivery import effective_telegram_bot_token
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.utils.logger import configure_structured_logging, get_obs_logger
from routers.db_write_compat import router as db_write_compat_router

try:
    from core.config import settings
except ImportError:
    from duckclaw.gateway.settings import get_gateway_settings

    settings = get_gateway_settings()

_log_level_name = (os.environ.get("DUCKCLAW_LOG_LEVEL") or "INFO").strip().upper()
_log_level = getattr(logging, _log_level_name, logging.INFO)
configure_structured_logging(level=_log_level)
_gateway_log = logging.getLogger("duckclaw.gateway")
_obs_log = get_obs_logger()

_gateway_log.info(
    "Gateway startup: gateway_db_path=%s DUCKCLAW_PM2_MATCHED_APP_NAME=%s",
    get_gateway_db_path() or "(unset)",
    (os.environ.get("DUCKCLAW_PM2_MATCHED_APP_NAME") or "").strip() or "(unset)",
)
try:
    from duckclaw.integrations.telegram.integration_gate import telegram_integration_env_configured

    if telegram_integration_env_configured():
        from duckclaw.integrations.telegram.compact_webhook_routes import load_path_webhook_bindings_from_env

        _compact = load_path_webhook_bindings_from_env()
        if _compact:
            _gateway_log.info(
                "telegram path multiplex (integración): %s ruta(s): %s",
                len(_compact),
                ", ".join(b.webhook_path for b in _compact),
            )
except ValueError as _compact_exc:
    _gateway_log.error(
        "DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES inválido; rutas por path no montadas: %s",
        _compact_exc,
    )
except Exception:
    pass

# ── Re-exports con prefijo _ para compatibilidad (tests, admin, webhooks) ─────
_resolve_chat_session_id = resolve_chat_session_id
_invoke_chat = invoke_chat
_effective_tenant_id = effective_tenant_id
_dedicated_gateway_vault_db_path = dedicated_gateway_vault_db_path
_admin_visual_fields_from_invoke_result = admin_visual_fields_from_invoke_result
_persist_admin_fly_charts = persist_admin_fly_charts
_authorize_or_reject = authorize_or_reject

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API unificada para agentes, consola admin y escrituras DuckDB.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_gateway_middleware(app)

# ── Routers Gateway ───────────────────────────────────────────────────────────
app.include_router(health_router)
app.include_router(homeostasis_router)
app.include_router(agent_routes_router)
app.include_router(agent_chat_router)
app.include_router(db_read_router)
app.include_router(db_write_compat_router)

# ── Telegram inbound webhook (integración nativa) ────────────────────────────

try:
    from routers.telegram_inbound_webhook import build_telegram_inbound_webhook_router

    app.include_router(
        build_telegram_inbound_webhook_router(
            invoke_agent_chat=invoke_chat,
            resolve_effective_telegram_bot_token=effective_telegram_bot_token,
        )
    )
except ImportError as _tg_imp_err:
    _gateway_log.error(
        "Telegram webhook router omitido (import falló). Los POST /api/v1/telegram/* devolverán 404: %s",
        _tg_imp_err,
        exc_info=True,
    )

try:
    from routers.discord_inbound_webhook import build_discord_interactions_router

    app.include_router(
        build_discord_interactions_router(
            invoke_agent_chat=invoke_chat,
            app_state_holder=app.state,
        )
    )
except ImportError:
    pass

try:
    from routers.admin import router as admin_router

    app.include_router(admin_router)
except ImportError as _admin_imp_err:
    _gateway_log.error("Admin router omitido: %s", _admin_imp_err)

try:
    from routers.admin_domains.mcp_connectors import oauth_callback_public

    @app.get("/api/v1/oauth/callback", include_in_schema=False)
    async def notion_oauth_callback_alias(
        code: str = "",
        state: str = "",
        error: str = "",
        error_description: str = "",
    ):
        return await oauth_callback_public(
            code=code,
            state=state,
            error=error,
            error_description=error_description,
        )
except ImportError as _oauth_alias_err:
    _gateway_log.warning("OAuth callback alias omitido: %s", _oauth_alias_err)

try:
    from routers.sensory import router as sensory_router

    app.include_router(sensory_router)
except ImportError as _sensory_imp_err:
    _gateway_log.warning("Sensory router omitido: %s", _sensory_imp_err)

try:
    from duckclaw.graphs.novnc_routes import build_novnc_router

    app.include_router(
        build_novnc_router(),
        prefix="/api/v1/sandbox/novnc",
        tags=["sandbox-novnc"],
    )
except ImportError:
    pass
