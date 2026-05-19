# services/api-gateway/core/telegram_multipart_tail_dispatch_async.py
"""Despacho de la cola de texto (partes 2..N) hacia Telegram vía Bot API nativa o MCP."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

_log = logging.getLogger("duckclaw.gateway.telegram_multipart_tail")


def resolve_telegram_multipart_tail_delivery_mode(explicit: str | None) -> str:
    """Siempre ``native`` (Bot API o MCP en capas superiores)."""
    if explicit and explicit.strip().lower() not in ("native", ""):
        _log.warning(
            "multipart tail: modo %r ignorado; solo se admite entrega nativa",
            explicit,
        )
    return "native"


async def dispatch_telegram_multipart_tail_async(
    *,
    tail_plain: str,
    session_id: str,
    user_id: str,
    telegram_multipart_tail_delivery: str | None,
    effective_telegram_bot_token: Callable[[], str],
    telegram_mcp: Optional[Any] = None,
    redis_client: Optional[Any] = None,
    tenant_id: str = "default",
) -> None:
    raw = (tail_plain or "").strip()
    if not raw:
        return
    _ = resolve_telegram_multipart_tail_delivery_mode(telegram_multipart_tail_delivery)

    if telegram_mcp is not None:
        try:
            from duckclaw.forge.skills.telegram_mcp_bridge import send_long_plain_via_mcp_chunks

            from core.telegram_mcp_dlq import push_telegram_mcp_dlq

            ok = await send_long_plain_via_mcp_chunks(
                telegram_mcp.session,
                chat_id=str(session_id),
                plain_text=raw,
            )
            if ok:
                _log.info("multipart tail: entregado vía MCP chat_id=%s", session_id)
                return
            await push_telegram_mcp_dlq(
                redis_client,
                tenant_id=tenant_id,
                chat_id=str(session_id),
                tool="telegram_send_message",
                args={"chat_id": str(session_id), "text": "<multipart tail>", "parse_mode": "MarkdownV2"},
                error="send_long_plain_via_mcp_chunks returned failure",
            )
            _log.warning("multipart tail: MCP falló; se intenta Bot API chat_id=%s", session_id)
        except Exception as exc:  # noqa: BLE001
            _log.warning("multipart tail: excepción MCP (%s); fallback Bot API", exc)
            try:
                from core.telegram_mcp_dlq import push_telegram_mcp_dlq

                await push_telegram_mcp_dlq(
                    redis_client,
                    tenant_id=tenant_id,
                    chat_id=str(session_id),
                    tool="telegram_send_message",
                    args={"chat_id": str(session_id)},
                    error=str(exc)[:2000],
                )
            except Exception:
                pass

    token = (effective_telegram_bot_token() or "").strip()
    if not token:
        _log.warning("multipart tail: falta TELEGRAM_BOT_TOKEN (o token del bot en rutas compactas)")
        return
    from duckclaw.integrations.telegram import TelegramBotApiAsyncClient

    client = TelegramBotApiAsyncClient(token)
    await client.send_long_plain_text_as_markdown_v2_chunks(
        chat_id=session_id,
        plain_text=raw,
    )
