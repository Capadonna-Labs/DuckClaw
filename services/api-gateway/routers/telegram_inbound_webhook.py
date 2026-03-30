# services/api-gateway/routers/telegram_inbound_webhook.py
"""
Webhook entrante de Telegram (Bot API Update) → mismo pipeline que /api/v1/agent/.../chat.

Contrato: POST ``/api/v1/telegram/webhook`` con JSON de Update; validación opcional vía
``TELEGRAM_WEBHOOK_SECRET`` y cabecera ``X-Telegram-Bot-Api-Secret-Token``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request, status

from core.models import ChatRequest
from duckclaw.integrations.telegram import (
    TELEGRAM_WEBHOOK_SECRET_HTTP_HEADER,
    TelegramBotApiAsyncClient,
    is_valid_telegram_webhook_secret_token,
)

_log = logging.getLogger("duckclaw.gateway.telegram_inbound_webhook")

_TELEGRAM_WEBHOOK_DEDUPE_KEY_PREFIX = "duckclaw:dedupe:telegram:webhook:update"
_TELEGRAM_WEBHOOK_DEDUPE_TTL_SECONDS = 172800


def build_telegram_inbound_webhook_router(
    *,
    invoke_agent_chat: Callable[..., Awaitable[Any]],
    resolve_effective_telegram_bot_token: Callable[[], str],
) -> APIRouter:
    """
    Factory para no importar ``main`` desde este módulo (evita ciclos).

    - invoke_agent_chat: típicamente ``_invoke_chat`` del gateway.
    """

    router = APIRouter(prefix="/api/v1/telegram", tags=["telegram-inbound-webhook"])

    @router.post("/webhook")
    async def telegram_bot_update_webhook(request: Request) -> dict[str, str]:
        header_secret = request.headers.get(TELEGRAM_WEBHOOK_SECRET_HTTP_HEADER)
        if not is_valid_telegram_webhook_secret_token(header_secret):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "type": "about:blank",
                    "title": "Forbidden",
                    "status": 403,
                    "detail": "Secreto de webhook de Telegram inválido o ausente.",
                },
            )

        try:
            body = await request.json()
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "type": "about:blank",
                    "title": "Bad Request",
                    "status": 400,
                    "detail": "Cuerpo JSON inválido.",
                },
            )

        update_id = body.get("update_id")
        redis_client = getattr(request.app.state, "redis", None)
        if update_id is not None and redis_client is not None:
            dedupe_key = f"{_TELEGRAM_WEBHOOK_DEDUPE_KEY_PREFIX}:{update_id}"
            try:
                first_time = await redis_client.set(
                    dedupe_key,
                    "1",
                    nx=True,
                    ex=_TELEGRAM_WEBHOOK_DEDUPE_TTL_SECONDS,
                )
                if not first_time:
                    return {"ok": "true"}
            except Exception as exc:  # noqa: BLE001
                _log.warning("telegram webhook dedupe omitido (redis): %s", exc)

        msg = body.get("message") or body.get("edited_message")
        if not isinstance(msg, dict):
            return {"ok": "true"}

        chat = msg.get("chat") or {}
        if not isinstance(chat, dict):
            return {"ok": "true"}
        chat_id = chat.get("id")
        if chat_id is None:
            return {"ok": "true"}

        text = (msg.get("text") or msg.get("caption") or "").strip()
        from_user = msg.get("from") if isinstance(msg.get("from"), dict) else {}
        user_id_raw = from_user.get("id")
        user_id = str(user_id_raw if user_id_raw is not None else chat_id)
        username = str(
            from_user.get("username")
            or from_user.get("first_name")
            or from_user.get("last_name")
            or "Usuario"
        )
        chat_type = str(chat.get("type") or "private")

        worker_id = (os.environ.get("DUCKCLAW_TELEGRAM_DEFAULT_WORKER") or "finanz").strip() or "finanz"
        tenant_id = (os.environ.get("DUCKCLAW_TELEGRAM_DEFAULT_TENANT") or "default").strip() or "default"

        payload = ChatRequest(
            message=text,
            chat_id=str(chat_id),
            user_id=user_id,
            username=username,
            chat_type=chat_type,
            tenant_id=tenant_id,
        )

        session_id = str(chat_id)

        try:
            result = await invoke_agent_chat(
                payload,
                worker_id,
                session_id,
                tenant_id,
                redis_client=redis_client,
                telegram_multipart_tail_delivery="native",
            )
        except HTTPException as exc:
            detail = exc.detail
            if isinstance(detail, dict):
                msg_err = str(detail.get("detail") or detail)
            else:
                msg_err = str(detail)
            _log.warning("telegram webhook invoke falló: %s", msg_err)
            token = (resolve_effective_telegram_bot_token() or "").strip()
            if token and msg_err:
                try:
                    client = TelegramBotApiAsyncClient(token)
                    await client.send_message(
                        chat_id=chat_id,
                        text=msg_err[:3900],
                        parse_mode=None,
                    )
                except Exception as send_exc:  # noqa: BLE001
                    _log.warning("telegram webhook no pudo enviar error al usuario: %s", send_exc)
            return {"ok": "true"}

        reply = (result.get("response") or "").strip() if isinstance(result, dict) else ""
        if not reply:
            return {"ok": "true"}

        token = (resolve_effective_telegram_bot_token() or "").strip()
        if not token:
            _log.warning("telegram webhook: hay respuesta pero falta TELEGRAM_BOT_TOKEN")
            return {"ok": "true"}

        client = TelegramBotApiAsyncClient(token)
        await client.send_message(chat_id=chat_id, text=reply, parse_mode="MarkdownV2")
        return {"ok": "true"}

    return router
