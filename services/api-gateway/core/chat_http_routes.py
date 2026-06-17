"""Rutas HTTP POST /api/v1/agent/*/chat."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from core.agent_routes import effective_tenant_id
from core.chat_reply_format import chat_identity_label
from core.models import ChatRequest
from core.telegram_delivery import deliver_outbound_by_channel
from duckclaw.channels import GatewayDeliveryContext
from duckclaw.forge.team_env import default_worker_id_from_env
from duckclaw.utils.logger import format_chat_id_for_terminal, set_log_context

try:
    from core.config import settings
except ImportError:
    from duckclaw.gateway.settings import get_gateway_settings

    settings = get_gateway_settings()

_gateway_log = logging.getLogger("duckclaw.gateway")

router = APIRouter(tags=["agent"])


def _register_agent_chat_routes(*, invoke_chat: Any, invoke_chat_sse_body: Any) -> None:
    @router.post("/api/v1/agent/chat")
    @router.post("/api/v1/agent/{worker_id}/chat")
    async def agent_chat(
        http_request: Request,
        worker_id: Optional[str] = None,
        body: ChatRequest | None = None,
    ):
        from core.chat_session import resolve_chat_session_id

        if body is None:
            body = ChatRequest(
                message="",
                chat_id="default",
                user_id="system",
                username="system",
                chat_type="private",
            )
        session_id, session_source = resolve_chat_session_id(body, http_request)
        body_tid = (body.tenant_id or "").strip() or "default"
        hdr_tid = (http_request.headers.get("X-Tenant-Id") or "").strip()
        if body_tid.lower() == "default" and hdr_tid:
            body_tid = hdr_tid
        tenant_id = effective_tenant_id(None if body_tid.lower() == "default" else body_tid)
        chat_ident = chat_identity_label(session_id, body.username)
        set_log_context(tenant_id=tenant_id, worker_id="manager", chat_id=chat_ident)
        if session_source == "default" and not (body.chat_id or "").strip():
            _gateway_log.warning(
                "[session] chat_id/session_id ausente; usando 'default' (source=%s). "
                "El estado por chat (/sandbox) no coincidirá con otros mensajes. "
                "Añade chat_id al body, ?chat_id= en la URL, o cabecera X-Chat-Id. "
                "| chat=%s",
                session_source,
                format_chat_id_for_terminal(session_id),
            )
        else:
            _gateway_log.info(
                "[session] chat_id resolved: %s (source=%s)",
                format_chat_id_for_terminal(chat_ident),
                session_source,
            )
        redis_client = getattr(http_request.app.state, "redis", None)
        tg_mcp = getattr(http_request.app.state, "telegram_mcp", None)
        dc_http = GatewayDeliveryContext.from_legacy_telegram(
            telegram_multipart_tail_delivery=None,
            telegram_mcp=tg_mcp,
            telegram_forced_vault_db_path=None,
            outbound_telegram_bot_token=None,
        )
        deliver_outbound_raw = (http_request.query_params.get("deliver_outbound") or "").strip().lower()
        deliver_outbound = deliver_outbound_raw in ("1", "true", "yes", "on")
        stream = bool(body.stream) or (
            (http_request.query_params.get("stream") or "").strip().lower() in ("1", "true", "yes", "on")
        )
        invoke_kw = {
            "redis_client": redis_client,
            "telegram_mcp": tg_mcp,
        }
        eff_worker = worker_id or default_worker_id_from_env()
        if stream:
            from core.sse_stream import SSE_HEADERS

            return StreamingResponse(
                invoke_chat_sse_body(
                    body,
                    eff_worker,
                    session_id,
                    tenant_id,
                    http_request=http_request,
                    invoke_chat=invoke_chat,
                    **invoke_kw,
                ),
                media_type="text/event-stream",
                headers=dict(SSE_HEADERS),
            )
        result = await invoke_chat(
            body,
            eff_worker,
            session_id=session_id,
            tenant_id=tenant_id,
            **invoke_kw,
        )
        if deliver_outbound:
            await _maybe_deliver_outbound(
                result=result,
                body=body,
                session_id=session_id,
                worker_id=worker_id or "",
                tenant_id=tenant_id,
                dc_http=dc_http,
            )
        fb = (os.getenv("DUCKCLAW_CHAT_OUTBOUND_ON_CLIENT_DISCONNECT", "true").strip().lower())
        if fb in ("1", "true", "yes", ""):
            await _outbound_on_disconnect(
                http_request=http_request,
                result=result,
                body=body,
                session_id=session_id,
                worker_id=worker_id or "",
                tenant_id=tenant_id,
                tg_mcp=tg_mcp,
            )
        return result


async def _maybe_deliver_outbound(
    *,
    result: Any,
    body: ChatRequest,
    session_id: str,
    worker_id: str,
    tenant_id: str,
    dc_http: GatewayDeliveryContext,
) -> None:
    try:
        resp_text = (result.get("response") or "").strip() if isinstance(result, dict) else ""
        if not resp_text:
            return
        from core.goals_proactive_delivery import resolve_notify_channel, should_deliver_telegram

        notify_deliver = resolve_notify_channel(body)
        if not should_deliver_telegram(notify_deliver, session_id):
            return
        uid_out = (body.user_id or "").strip() or session_id
        loop = asyncio.get_running_loop()
        redis_url = str(settings.REDIS_URL)
        dc_deliver = GatewayDeliveryContext(
            channel=dc_http.channel,
            telegram_multipart_tail_delivery=dc_http.telegram_multipart_tail_delivery,
            telegram_mcp=dc_http.telegram_mcp,
            telegram_forced_vault_db_path=dc_http.telegram_forced_vault_db_path,
            outbound_bot_token=dc_http.outbound_bot_token,
            prefer_native_bot_api=True,
        )
        await loop.run_in_executor(
            None,
            lambda: deliver_outbound_by_channel(
                dc_deliver,
                chat_id=session_id,
                user_id=uid_out,
                text=resp_text,
                worker_id=worker_id,
                tenant_id=tenant_id,
                redis_url=redis_url,
                prefer_native_bot_api=True,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        _gateway_log.warning("agent_chat forced outbound failed: %s", exc)


async def _outbound_on_disconnect(
    *,
    http_request: Request,
    result: Any,
    body: ChatRequest,
    session_id: str,
    worker_id: str,
    tenant_id: str,
    tg_mcp: Any,
) -> None:
    try:
        if not await http_request.is_disconnected():
            return
        resp_text = (result.get("response") or "").strip() if isinstance(result, dict) else ""
        if not resp_text:
            return
        uid_fb = (body.user_id or "").strip() or session_id
        _gateway_log.info(
            "outbound fallback: cliente desconectado; entrega async a Telegram "
            "(nativo o webhook) chat_id=%s len=%s",
            format_chat_id_for_terminal(session_id),
            len(resp_text),
        )
        loop = asyncio.get_running_loop()
        redis_url = str(settings.REDIS_URL)
        dc_fb = GatewayDeliveryContext.from_legacy_telegram(
            telegram_multipart_tail_delivery=None,
            telegram_mcp=tg_mcp,
            telegram_forced_vault_db_path=None,
            outbound_telegram_bot_token=None,
        )
        await loop.run_in_executor(
            None,
            lambda: deliver_outbound_by_channel(
                dc_fb,
                chat_id=session_id,
                user_id=uid_fb,
                text=resp_text,
                worker_id=worker_id,
                tenant_id=tenant_id,
                redis_url=redis_url,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        _gateway_log.warning("outbound fallback: no se pudo comprobar/enviar: %s", exc)
