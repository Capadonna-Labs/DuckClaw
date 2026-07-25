# services/api-gateway/main.py
"""
DuckClaw API Gateway — Microservicio unificado.

Punto de entrada único para Telegram (webhook/long polling), clientes HTTP, Angular y escrituras a DuckDB.
Endpoints: /api/v1/agent/chat, /api/v1/db/write, homeostasis, system health.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT_FOR_DB = Path(__file__).resolve().parent.parent.parent
os.environ.setdefault("DUCKCLAW_REPO_ROOT", str(_REPO_ROOT_FOR_DB))

from core.gateway_bootstrap import apply_gateway_bootstrap

apply_gateway_bootstrap()

from core.agent_chat import invoke_chat, resolve_chat_session_id
from core.agent_routes import effective_tenant_id
from core.chat_auth import authorize_or_reject
from core.chat_reply_format import clean_agent_response
from core.chat_visual_artifacts import (
    admin_visual_fields_from_invoke_result,
    persist_admin_fly_charts,
)
from core.gateway_vault import dedicated_gateway_vault_db_path
from gateway_app_factory import app

# ── Re-exports con prefijo _ para compatibilidad (tests, admin, webhooks) ─────
_resolve_chat_session_id = resolve_chat_session_id
_invoke_chat = invoke_chat
_effective_tenant_id = effective_tenant_id
_dedicated_gateway_vault_db_path = dedicated_gateway_vault_db_path
_admin_visual_fields_from_invoke_result = admin_visual_fields_from_invoke_result
_persist_admin_fly_charts = persist_admin_fly_charts
_authorize_or_reject = authorize_or_reject
