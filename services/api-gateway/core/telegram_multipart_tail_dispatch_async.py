# services/api-gateway/core/telegram_multipart_tail_dispatch_async.py
"""Despacho de la cola de texto (partes 2..N) hacia Telegram: Bot API nativa o webhook n8n."""

from __future__ import annotations

import asyncio
import logging
import os
from functools import partial
from typing import Any, Callable, Optional

_log = logging.getLogger("duckclaw.gateway.telegram_multipart_tail")


def resolve_telegram_multipart_tail_delivery_mode(explicit: str | None) -> str:
    """
    ``native`` | ``n8n``. Por defecto **native** (Bot API directa o MCP arriba).
    Solo n8n si ``DUCKCLAW_TELEGRAM_OUTBOUND_VIA=n8n`` y existe ``N8N_OUTBOUND_WEBHOOK_URL``.

    El legado ``DUCKCLAW_TELEGRAM_NATIVE_SEND=0`` + n8n queda detrás de
    ``DUCKCLAW_TELEGRAM_LEGACY_N8N_WEBHOOK=1`` para no depender de n8n por defecto.
    """
    if explicit in ("native", "n8n"):
        return explicit
    n8n_url = (os.getenv("N8N_OUTBOUND_WEBHOOK_URL") or "").strip()
    via = (os.getenv("DUCKCLAW_TELEGRAM_OUTBOUND_VIA") or "").strip().lower()
    if via == "n8n" and n8n_url:
        _log.info("telegram multipart tail: modo n8n (DUCKCLAW_TELEGRAM_OUTBOUND_VIA=n8n)")
        return "n8n"
    legacy = os.getenv("DUCKCLAW_TELEGRAM_LEGACY_N8N_WEBHOOK", "").strip().lower() in ("1", "true", "yes")
    force_webhook = os.getenv("DUCKCLAW_TELEGRAM_NATIVE_SEND", "").strip().lower() in ("0", "false", "no", "off")
    if legacy and force_webhook and n8n_url:
        _log.info("telegram multipart tail: modo n8n (legado LEGACY_N8N_WEBHOOK + NATIVE_SEND off)")
        return "n8n"
    return "native"


async def dispatch_telegram_multipart_tail_async(
    *,
    tail_plain: str,
    session_id: str,
    user_id: str,
    telegram_multipart_tail_delivery: str | None,
    effective_telegram_bot_token: Callable[[], str],
    n8n_outbound_push_sync: Callable[..., None],
    telegram_mcp: Optional[Any] = None,
    redis_client: Optional[Any] = None,
    tenant_id: str = "default",
) -> None:
    raw = (tail_plain or "").strip()
    if not raw:
        return

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
            _log.warning("multipart tail: MCP falló; se intenta nativo/n8n chat_id=%s", session_id)
        except Exception as exc:  # noqa: BLE001
            _log.warning("multipart tail: excepción MCP (%s); fallback nativo/n8n", exc)
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

    mode = resolve_telegram_multipart_tail_delivery_mode(telegram_multipart_tail_delivery)
    if mode == "n8n" and not (os.getenv("N8N_OUTBOUND_WEBHOOK_URL") or "").strip():
        mode = "native"
        _log.warning("multipart tail: modo n8n pero N8N_OUTBOUND_WEBHOOK_URL vacío; usando nativo")
    if mode == "native":
        token = (effective_telegram_bot_token() or "").strip()
        if not token:
            _log.warning("multipart tail nativo: falta TELEGRAM_BOT_TOKEN")
            return
        from duckclaw.integrations.telegram import TelegramBotApiAsyncClient

        client = TelegramBotApiAsyncClient(token)
        await client.send_long_plain_text_as_markdown_v2_chunks(
            chat_id=session_id,
            plain_text=raw,
        )
        return
    await asyncio.get_running_loop().run_in_executor(
        None,
        partial(
            n8n_outbound_push_sync,
            chat_id=session_id,
            user_id=(user_id or "").strip() or session_id,
            text=raw,
        ),
    )
