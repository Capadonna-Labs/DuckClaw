# services/api-gateway/core/telegram_compact_webhook_routes.py
"""Re-export: implementación en duckclaw-shared (un solo parse de rutas compactas)."""

from duckclaw.integrations.telegram.compact_webhook_routes import (  # noqa: F401
    TelegramCompactWebhookRoute,
    TelegramPathWebhookBinding,
    compact_route_to_path_binding,
    fastapi_relative_path,
    known_compact_bot_names,
    load_path_webhook_bindings_from_env,
    parse_compact_telegram_webhook_routes,
    serialize_compact_telegram_webhook_routes,
)

__all__ = [
    "TelegramCompactWebhookRoute",
    "TelegramPathWebhookBinding",
    "compact_route_to_path_binding",
    "fastapi_relative_path",
    "known_compact_bot_names",
    "load_path_webhook_bindings_from_env",
    "parse_compact_telegram_webhook_routes",
    "serialize_compact_telegram_webhook_routes",
]
