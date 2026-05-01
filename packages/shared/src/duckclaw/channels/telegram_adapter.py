"""Adaptador Telegram: contexto de entrega explícito para el gateway (wrapper sin copiar lógica)."""

from __future__ import annotations

from typing import Any

from duckclaw.channels.delivery import GatewayDeliveryContext


def build_telegram_webhook_delivery_context(
    *,
    telegram_multipart_tail_delivery: str | None,
    telegram_mcp: Any | None,
    telegram_forced_vault_db_path: str | None,
    outbound_telegram_bot_token: str | None,
) -> GatewayDeliveryContext:
    """Misma semántica que kwargs legacy pasados desde ``telegram_inbound_webhook``."""
    return GatewayDeliveryContext.from_legacy_telegram(
        telegram_multipart_tail_delivery=telegram_multipart_tail_delivery,
        telegram_mcp=telegram_mcp,
        telegram_forced_vault_db_path=telegram_forced_vault_db_path,
        outbound_telegram_bot_token=outbound_telegram_bot_token,
    )
