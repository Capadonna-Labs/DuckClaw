# packages/shared/src/duckclaw/integrations/telegram/__init__.py
"""Integración Telegram: long polling, webhook (cabecera secreta), cliente Bot API async."""

from duckclaw.integrations.telegram.telegram_bot_api_async_client import TelegramBotApiAsyncClient
from duckclaw.integrations.telegram.telegram_outbound_sync import (
    normalize_telegram_chat_id_for_bot_api,
    send_long_plain_text_markdown_v2_chunks_sync,
    send_message_markdown_v2_sync,
)
from duckclaw.integrations.telegram.telegram_long_polling_bot_base import (
    TelegramBotBase,
    TelegramLongPollingBotBase,
)
from duckclaw.integrations.telegram.outbound_token_context import (
    effective_telegram_bot_token_outbound,
    telegram_bot_token_override,
)
from duckclaw.integrations.telegram.telegram_agent_token import (
    PM2_GATEWAY_APP_TO_WORKER_ID,
    canonical_manifest_worker_id,
    resolve_telegram_token_from_flat_env,
    resolve_telegram_token_for_worker_id,
    telegram_agent_token_env_name,
    telegram_token_from_pm2_env_dict,
)
from duckclaw.integrations.telegram.telegram_webhook_secret_header import (
    TELEGRAM_WEBHOOK_SECRET_HTTP_HEADER,
    is_valid_telegram_webhook_secret_token,
    telegram_webhook_secret_expected_from_env,
)

__all__ = [
    "PM2_GATEWAY_APP_TO_WORKER_ID",
    "canonical_manifest_worker_id",
    "TELEGRAM_WEBHOOK_SECRET_HTTP_HEADER",
    "TelegramBotApiAsyncClient",
    "TelegramBotBase",
    "TelegramLongPollingBotBase",
    "effective_telegram_bot_token_outbound",
    "is_valid_telegram_webhook_secret_token",
    "normalize_telegram_chat_id_for_bot_api",
    "send_long_plain_text_markdown_v2_chunks_sync",
    "send_message_markdown_v2_sync",
    "telegram_bot_token_override",
    "resolve_telegram_token_from_flat_env",
    "resolve_telegram_token_for_worker_id",
    "telegram_agent_token_env_name",
    "telegram_token_from_pm2_env_dict",
    "telegram_webhook_secret_expected_from_env",
]
