"""URN opcionales para session_id (compatibilidad Telegram plano)."""

from __future__ import annotations

import os


def urn_sessions_enabled() -> bool:
    return (os.environ.get("DUCKCLAW_CHANNEL_URN_SESSIONS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def build_telegram_session_id(telegram_chat_id: str) -> str:
    cid = str(telegram_chat_id or "").strip()
    if urn_sessions_enabled():
        if cid.startswith("telegram:"):
            return cid
        return f"telegram:{cid}"
    return cid


def build_discord_session_id(guild_id: str, channel_id: str, user_id: str) -> str:
    g, c, u = (str(guild_id or "").strip(), str(channel_id or "").strip(), str(user_id or "").strip())
    if urn_sessions_enabled():
        return f"discord:{g}:{c}:{u}"
    return f"discord:{g}:{c}:{u}"
