"""Resolución de tenant y usuario Telegram para el playground admin."""

from __future__ import annotations

import os


def gateway_effective_tenant_id(request_tenant: str | None) -> str:
    """Misma resolución que ``main._effective_tenant_id``."""
    import main as gateway_main

    raw = (request_tenant or "").strip() or "default"
    return gateway_main._effective_tenant_id(raw)


def playground_telegram_user_id(override: str | None = None) -> str:
    """ID Telegram del operador (mismo que Telegram Guard y /workers en DM)."""
    return (
        (override or "").strip()
        or (os.environ.get("DUCKCLAW_OWNER_ID") or os.environ.get("DUCKCLAW_ADMIN_CHAT_ID") or "")
        .strip()
    )
