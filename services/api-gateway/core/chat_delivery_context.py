"""Fusión de ``GatewayDeliveryContext`` con kwargs legacy de Telegram."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from duckclaw.channels import GatewayDeliveryContext


def merge_delivery_context(
    delivery_context: GatewayDeliveryContext | None,
    *,
    telegram_multipart_tail_delivery: str | None = None,
    telegram_mcp: Any = None,
    telegram_forced_vault_db_path: str | None = None,
    outbound_telegram_bot_token: str | None = None,
) -> GatewayDeliveryContext:
    if delivery_context is not None:
        dc = delivery_context
    else:
        dc = GatewayDeliveryContext.from_legacy_telegram(
            telegram_multipart_tail_delivery=telegram_multipart_tail_delivery,
            telegram_mcp=telegram_mcp,
            telegram_forced_vault_db_path=telegram_forced_vault_db_path,
            outbound_telegram_bot_token=outbound_telegram_bot_token,
        )
    channel = (dc.channel or "telegram").strip().lower()
    if channel != "telegram":
        return dc
    patch: dict[str, Any] = {}
    if telegram_multipart_tail_delivery is not None:
        patch["telegram_multipart_tail_delivery"] = telegram_multipart_tail_delivery
    if telegram_mcp is not None:
        patch["telegram_mcp"] = telegram_mcp
    if telegram_forced_vault_db_path is not None:
        patch["telegram_forced_vault_db_path"] = telegram_forced_vault_db_path
    if outbound_telegram_bot_token is not None:
        patch["outbound_bot_token"] = (outbound_telegram_bot_token or "").strip() or None
    if patch:
        return replace(dc, **patch)
    return dc
