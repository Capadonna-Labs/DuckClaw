# packages/shared/src/duckclaw/integrations/telegram/telegram_long_polling_bot_base.py
"""Base para bots en long polling (python-telegram-bot)."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any


class TelegramLongPollingBotBase(ABC):
    """
    Clase base: implementa ``build_application`` para PTB y delega mensajes a ``handle_message`` síncrono
    (patrón usado por duckclaw.graphs.telegram_bot).
    """

    def __init__(self, db: Any) -> None:
        self.db = db

    @abstractmethod
    def handle_message(self, update: Any) -> None:
        """Procesa un update con ``effective_message`` (texto, caption, comandos)."""

    def build_application(self, token: str) -> Any:
        try:
            from telegram.ext import ApplicationBuilder, MessageHandler, filters
        except ImportError as exc:
            raise ImportError(
                "Falta python-telegram-bot. Instala el extra: uv sync --extra telegram"
            ) from exc

        async def _on_text_or_caption(update: Any, context: Any) -> None:
            await asyncio.to_thread(self.handle_message, update)

        application = ApplicationBuilder().token(token).build()
        application.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, _on_text_or_caption))
        return application


# Alias histórico (scripts y paquete agents).
TelegramBotBase = TelegramLongPollingBotBase
