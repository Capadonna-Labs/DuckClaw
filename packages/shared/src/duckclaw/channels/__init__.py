"""Contratos agnósticos al canal de chat (Telegram, Discord, …)."""

from duckclaw.channels.delivery import GatewayDeliveryContext
from duckclaw.channels.routes import (
    ChannelRouteBinding,
    load_channel_route_bindings,
    resolve_discord_route,
)
from duckclaw.channels.telegram_adapter import build_telegram_webhook_delivery_context
from duckclaw.channels.types import ChannelName, DeliveryResult, NormalizedTurn
from duckclaw.channels.urn import build_discord_session_id, build_telegram_session_id, urn_sessions_enabled

__all__ = [
    "GatewayDeliveryContext",
    "ChannelRouteBinding",
    "load_channel_route_bindings",
    "resolve_discord_route",
    "build_telegram_webhook_delivery_context",
    "ChannelName",
    "DeliveryResult",
    "NormalizedTurn",
    "build_discord_session_id",
    "build_telegram_session_id",
    "urn_sessions_enabled",
]
