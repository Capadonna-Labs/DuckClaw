# packages/shared/src/duckclaw/integrations/telegram/telegram_bot_api_async_client.py
"""Cliente async (httpx) para la Bot API de Telegram — sendMessage y troceado largo."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

import httpx

from duckclaw.utils.telegram_markdown_v2 import llm_markdown_to_telegram_html, plain_subchunks_for_telegram_html

_log = logging.getLogger("duckclaw.telegram_bot_api")

# Alineado con services/api-gateway (margen tras escape MarkdownV2).
_DEFAULT_OUTBOUND_PLAIN_CHUNK = 3600


class TelegramBotApiAsyncClient:
    """sendMessage asíncrono; reutilizable desde API Gateway y futuros workers."""

    def __init__(self, bot_token: str) -> None:
        token = (bot_token or "").strip()
        if not token:
            raise ValueError("TelegramBotApiAsyncClient requiere bot_token no vacío.")
        self._bot_id = token.split(":", 1)[0]
        self._token_fp = hashlib.sha1(token.encode("utf-8")).hexdigest()[:10]
        self._api_url = f"https://api.telegram.org/bot{token}"

    async def send_message(
        self,
        *,
        chat_id: int | str,
        text: str,
        parse_mode: str | None = "HTML",
        disable_web_page_preview: bool | None = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        # region agent log
        try:
            with open(
                "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
                "a",
                encoding="utf-8",
            ) as _df:
                _df.write(
                    json.dumps(
                        {
                            "sessionId": "c964f7",
                            "runId": "pre-fix",
                            "hypothesisId": "H12_async_client_token",
                            "location": "packages/shared/src/duckclaw/integrations/telegram/telegram_bot_api_async_client.py:send_message",
                            "message": "about_to_send",
                            "data": {
                                "chat_id": str(chat_id),
                                "bot_id": str(self._bot_id),
                                "token_fp": str(self._token_fp),
                                "text_len": len(str(text or "")),
                            },
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
        # endregion
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

    async def leave_chat(self, *, chat_id: int | str) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": chat_id}
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            response = await client.post(f"{self._api_url}/leaveChat", json=payload)
            try:
                data = response.json() if response.content else {}
            except Exception:
                data = {}
            if not response.is_success or not data.get("ok"):
                _log.warning(
                    "Telegram leaveChat falló: status=%s body=%s",
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
        Trocea texto plano y envía varios sendMessage con parse_mode HTML
        (legibilidad: sin barras de escape MarkdownV2 en puntuación).
        """
        raw = (plain_text or "").strip()
        if not raw:
            return
        chunks = plain_subchunks_for_telegram_html(raw)
        if not chunks:
            chunks = [raw]
        total = len(chunks)
        for idx, part in enumerate(chunks):
            prefix = f"[{idx + 1}/{total}]\n" if total > 1 else ""
            safe = llm_markdown_to_telegram_html(prefix + part)
            await self.send_message(chat_id=chat_id, text=safe, parse_mode="HTML")
