# services/api-gateway/core/telegram_multipart_tail_dispatch_async.py
"""Despacho de la cola de texto (partes 2..N) hacia Telegram: Bot API nativa o webhook n8n."""

from __future__ import annotations

import asyncio
import logging
import os
from functools import partial
from typing import Any, Callable

_log = logging.getLogger("duckclaw.gateway.telegram_multipart_tail")


def resolve_telegram_multipart_tail_delivery_mode(explicit: str | None) -> str:
    """``native`` | ``n8n`` según override explícito o variables de entorno."""
    if explicit in ("native", "n8n"):
        return explicit
    use_native = os.getenv("DUCKCLAW_TELEGRAM_NATIVE_SEND", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    n8n_url = (os.getenv("N8N_OUTBOUND_WEBHOOK_URL") or "").strip()
    if use_native:
        return "native"
    if n8n_url:
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
) -> None:
    raw = (tail_plain or "").strip()
    if not raw:
        return
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
