"""Preparación del contexto de invoke (auth, historial, bóveda) antes del grafo."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

from core.agent_routes import effective_tenant_id
from core.chat_auth import resolve_authorize_or_reject
from core.chat_history import (
    gateway_chat_history_enabled,
    normalize_history_list,
    redis_load_chat_history,
)
from core.chat_reply_format import chat_identity_label, truncate_log
from core.chat_vault_resolution import resolve_chat_vault_db_path
from core.models import ChatRequest
from duckclaw.channels import GatewayDeliveryContext
from duckclaw.utils.logger import get_obs_logger, log_req, set_log_context

_obs_log = get_obs_logger()


@dataclass(frozen=True)
class PreparedChatInvoke:
    payload: ChatRequest
    worker_id: str
    session_id: str
    tenant_id: str
    message: str
    user_incoming: str
    chat_type: str
    username: str
    user_id: str
    vault_user_id: str
    vault_db_path: str
    telegram_acl_for_guard: str | None
    delivery_context: GatewayDeliveryContext
    history_for_model: list[dict[str, Any]]
    is_system_prompt: bool
    skip_session_lock: bool
    shared_db_path: str | None
    auth_policy: str
    is_owner: bool
    chat_ident: str
    payload_vault: str


async def prepare_chat_invoke(
    payload: ChatRequest,
    worker_id: str,
    session_id: str,
    tenant_id: str,
    delivery_context: GatewayDeliveryContext,
    *,
    redis_client: Any = None,
) -> PreparedChatInvoke | dict[str, Any]:
    """Valida auth y carga historial. Retorna dict si el mensaje está vacío (respuesta temprana)."""
    message = (payload.message or "").strip()
    user_incoming = (getattr(payload, "user_incoming", None) or message or "").strip()
    session_id = (session_id or "default").strip() or "default"
    from duckclaw.graphs.chat_cancel import clear_chat_cancel

    clear_chat_cancel(session_id)
    tenant_id = effective_tenant_id(tenant_id)
    chat_type = (payload.chat_type or "private").strip().lower() or "private"
    username = (payload.username or "Usuario").strip() or "Usuario"
    user_id = (payload.user_id or "").strip()
    if not user_id and chat_type == "private":
        user_id = session_id
    vault_user_id = user_id or session_id
    payload_vault = (getattr(payload, "vault_db_path", None) or "").strip()
    vault_db_path, telegram_acl_for_guard = resolve_chat_vault_db_path(
        payload=payload,
        worker_id=worker_id,
        vault_user_id=vault_user_id,
        tenant_id=tenant_id,
        delivery_context=delivery_context,
    )

    history = payload.history or []
    is_system_prompt = bool(payload.is_system_prompt or False)
    skip_session_lock = bool(getattr(payload, "skip_session_lock", False) or False)
    msg_for_cb = message.strip()
    is_fly_command = msg_for_cb.startswith("/")
    if not is_system_prompt and not skip_session_lock and not is_fly_command:
        try:
            from harness_core.skills.emit_correction_delta import is_circuit_breaker_active

            if is_circuit_breaker_active(
                tenant_id,
                worker_id or "",
                redis_client=redis_client,
            ):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=(
                        "Meditate circuit breaker activo para este worker. "
                        "Revisa alertas admin (meditate_critical) antes de reanudar chats."
                    ),
                )
        except HTTPException:
            raise
        except Exception:
            pass

    shared_db_path = (payload.shared_db_path or "").strip() or None
    history_for_model = normalize_history_list(list(history))
    if (
        not is_system_prompt
        and redis_client is not None
        and gateway_chat_history_enabled()
        and not history_for_model
    ):
        history_for_model = await redis_load_chat_history(redis_client, tenant_id, session_id)

    chat_ident = chat_identity_label(session_id, username)
    set_log_context(tenant_id=tenant_id, worker_id="manager", chat_id=chat_ident)
    log_req(_obs_log, "%s", truncate_log(message), source="body")

    owner_user_id = (os.getenv("DUCKCLAW_OWNER_ID") or os.getenv("DUCKCLAW_ADMIN_CHAT_ID") or "").strip()
    is_owner = bool(owner_user_id and user_id and str(user_id).strip() == str(owner_user_id).strip())
    auth_policy = (delivery_context.auth_policy or "telegram_guard").strip()
    guard_required = auth_policy not in {"trusted_admin_console", "trusted_channel_route"}
    if not is_system_prompt and guard_required:
        await resolve_authorize_or_reject()(
            redis_client=redis_client,
            tenant_id=tenant_id,
            user_id=user_id,
            is_owner=is_owner,
            telegram_guard_acl_db_path=telegram_acl_for_guard,
        )

    if not is_system_prompt and not is_owner:
        from core.gateway_acl_db import ReadOnlyGatewayAclDb, get_gateway_acl_duckdb
        from duckclaw.shared_db_grants import path_is_under_shared_tree, user_may_access_shared_path

        acl_db = (
            ReadOnlyGatewayAclDb(telegram_acl_for_guard)
            if telegram_acl_for_guard
            else get_gateway_acl_duckdb()[0]
        )
        candidates = {
            s
            for s in ((shared_db_path or "").strip(), (os.getenv("DUCKCLAW_SHARED_DB_PATH") or "").strip())
            if s
        }
        for candidate in candidates:
            if not path_is_under_shared_tree(candidate):
                continue
            if not user_may_access_shared_path(
                acl_db,
                tenant_id=tenant_id,
                user_id=vault_user_id,
                shared_db_path=candidate,
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Sin permiso para acceder a la base de datos compartida configurada.",
                )

    if not message:
        return {
            "response": "No recibí ningún mensaje. Escribe tu consulta o comando (por ejemplo /tasks).",
            "session_id": session_id,
            "worker_id": worker_id,
            "elapsed_ms": 0,
        }

    return PreparedChatInvoke(
        payload=payload,
        worker_id=worker_id,
        session_id=session_id,
        tenant_id=tenant_id,
        message=message,
        user_incoming=user_incoming,
        chat_type=chat_type,
        username=username,
        user_id=user_id,
        vault_user_id=vault_user_id,
        vault_db_path=vault_db_path,
        telegram_acl_for_guard=telegram_acl_for_guard,
        delivery_context=delivery_context,
        history_for_model=history_for_model,
        is_system_prompt=is_system_prompt,
        skip_session_lock=skip_session_lock,
        shared_db_path=shared_db_path,
        auth_policy=auth_policy,
        is_owner=is_owner,
        chat_ident=chat_ident,
        payload_vault=payload_vault,
    )
