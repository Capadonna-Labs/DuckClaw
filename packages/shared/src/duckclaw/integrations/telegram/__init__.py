# packages/shared/src/duckclaw/integrations/telegram/__init__.py
"""Integración Telegram: long polling, webhook (cabecera secreta), cliente Bot API async."""

from duckclaw.integrations.telegram.telegram_bot_api_async_client import TelegramBotApiAsyncClient
from duckclaw.integrations.telegram.telegram_long_polling_bot_base import (
    TelegramBotBase,
    TelegramLongPollingBotBase,
)
from duckclaw.integrations.telegram.telegram_webhook_secret_header import (
    TELEGRAM_WEBHOOK_SECRET_HTTP_HEADER,
    is_valid_telegram_webhook_secret_token,
    telegram_webhook_secret_expected_from_env,
)

__all__ = [
    "TELEGRAM_WEBHOOK_SECRET_HTTP_HEADER",
    "TelegramBotApiAsyncClient",
    "TelegramBotBase",
    "TelegramLongPollingBotBase",
    "is_valid_telegram_webhook_secret_token",
    "telegram_webhook_secret_expected_from_env",
]
