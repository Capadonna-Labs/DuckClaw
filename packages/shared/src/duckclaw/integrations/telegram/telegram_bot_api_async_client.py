# packages/shared/src/duckclaw/integrations/telegram/telegram_bot_api_async_client.py
"""Cliente async (httpx) para la Bot API de Telegram — sendMessage y troceado largo."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from duckclaw.utils.telegram_markdown_v2 import escape_telegram_markdown_v2

_log = logging.getLogger("duckclaw.telegram_bot_api")

# Alineado con services/api-gateway (margen tras escape MarkdownV2).
_DEFAULT_OUTBOUND_PLAIN_CHUNK = 3600


class TelegramBotApiAsyncClient:
    """sendMessage asíncrono; reutilizable desde API Gateway y futuros workers."""

    def __init__(self, bot_token: str) -> None:
        token = (bot_token or "").strip()
        if not token:
            raise ValueError("TelegramBotApiAsyncClient requiere bot_token no vacío.")
        self._api_url = f"https://api.telegram.org/bot{token}"

    async def send_message(
        self,
        *,
        chat_id: int | str,
        text: str,
        parse_mode: str | None = "MarkdownV2",
        disable_web_page_preview: bool | None = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if disable_web_page_preview is not None:
            payload["disable_web_page_preview"] = disable_web_page_preview
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            response = await client.post(f"{self._api_url}/sendMessage", json=payload)
            data: dict[str, Any]
            try:
                data = response.json() if response.content else {}
            except Exception:
                data = {}
            if not response.is_success or not data.get("ok"):
                _log.warning(
                    "Telegram sendMessage falló: status=%s body=%s",
                    response.status_code,
                    data or response.text[:500],
                )
            return data

    async def send_long_plain_text_as_markdown_v2_chunks(
        self,
        *,
        chat_id: int | str,
        plain_text: str,
        max_plain_chunk: int = _DEFAULT_OUTBOUND_PLAIN_CHUNK,
    ) -> None:
        """
        Trocea texto plano, escapa MarkdownV2 por parte y envía varios sendMessage
        (mismo contrato que el webhook de salida n8n histórico).
        """
        raw = (plain_text or "").strip()
        if not raw:
            return
        chunks: list[str] = []
        i = 0
        n = len(raw)
        cap = max(256, min(max_plain_chunk, 3900))
        while i < n:
            chunks.append(raw[i : i + cap])
            i += cap
        if not chunks:
            chunks = [raw]
        total = len(chunks)
        for idx, part in enumerate(chunks):
            prefix = f"[{idx + 1}/{total}]\n" if total > 1 else ""
            escaped = escape_telegram_markdown_v2(prefix + part)
            await self.send_message(chat_id=chat_id, text=escaped, parse_mode="MarkdownV2")
