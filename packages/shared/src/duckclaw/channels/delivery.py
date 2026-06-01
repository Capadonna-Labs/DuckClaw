"""Contexto de entrega unificado para `_invoke_chat` y outbound."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GatewayDeliveryContext:
    """
    Sustituye progresivamente kwargs `telegram_*` en el gateway.
    channel: telegram | discord | …
    outbound_bot_token: token Bot API Telegram o Discord según canal.
    """

    channel: str = "telegram"
    telegram_multipart_tail_delivery: str | None = None
    telegram_mcp: Any | None = None
    telegram_forced_vault_db_path: str | None = None
    outbound_bot_token: str | None = None
    prefer_native_bot_api: bool = False
    auth_policy: str = "telegram_guard"
    discord_interaction_token: str | None = None
    discord_application_id: str | None = None
    discord_guild_id: str | None = None
    discord_channel_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_legacy_telegram(
        cls,
        *,
        telegram_multipart_tail_delivery: str | None,
        telegram_mcp: Any | None,
        telegram_forced_vault_db_path: str | None,
        outbound_telegram_bot_token: str | None,
    ) -> GatewayDeliveryContext:
        return cls(
            channel="telegram",
            telegram_multipart_tail_delivery=telegram_multipart_tail_delivery,
            telegram_mcp=telegram_mcp,
            telegram_forced_vault_db_path=telegram_forced_vault_db_path,
            outbound_bot_token=(outbound_telegram_bot_token or "").strip() or None,
            prefer_native_bot_api=False,
            auth_policy="telegram_guard",
        )

    @classmethod
    def trusted_admin_console(cls) -> GatewayDeliveryContext:
        """Authenticated Admin UI request; do not apply Telegram whitelist guard."""
        return cls(channel="http", auth_policy="trusted_admin_console")

    @classmethod
    def trusted_channel_route(cls, *, channel: str, **kwargs: Any) -> GatewayDeliveryContext:
        """Pre-authorized inbound route; channel-specific ACL was already enforced upstream."""
        return cls(channel=channel, auth_policy="trusted_channel_route", **kwargs)
