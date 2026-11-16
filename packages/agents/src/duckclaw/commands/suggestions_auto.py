"""Chat-scoped preference: admin UI suggestion chips Auto countdown."""

from __future__ import annotations

from typing import Any

from duckclaw.commands.chat_state import get_chat_state, set_chat_state_via_typed_command

# agent_config suffix under chat_{id}_*
SUGGESTIONS_AUTO_KEY = "suggestions_auto"


def suggestions_auto_enabled(db: Any, chat_id: Any) -> bool | None:
    """
    Return True/False when the agent (or UI) set an explicit preference; None = unset.
    Unset → admin UI falls back to browser localStorage.
    """
    raw = (get_chat_state(db, chat_id, SUGGESTIONS_AUTO_KEY) or "").strip().lower()
    if not raw:
        return None
    if raw in ("0", "off", "false", "no", "disabled"):
        return False
    if raw in ("1", "on", "true", "yes", "enabled"):
        return True
    return None


SUGGESTIONS_AUTO_SECONDS_KEY = "suggestions_auto_seconds"
AUTO_SECONDS_DEFAULT, AUTO_SECONDS_MIN, AUTO_SECONDS_MAX = 15, 3, 300


def clamp_auto_seconds(value: Any) -> int:
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return AUTO_SECONDS_DEFAULT
    return max(AUTO_SECONDS_MIN, min(AUTO_SECONDS_MAX, n))


def suggestions_auto_seconds(db: Any, chat_id: Any) -> int | None:
    """Countdown before Auto sends the recommended chip; None = unset (UI default)."""
    raw = (get_chat_state(db, chat_id, SUGGESTIONS_AUTO_SECONDS_KEY) or "").strip()
    return clamp_auto_seconds(raw) if raw else None


def set_suggestions_auto_seconds(db: Any, chat_id: Any, seconds: Any, *, tenant_id: str = "default") -> tuple[bool, str]:
    tid = str(tenant_id or "default").strip() or "default"
    return set_chat_state_via_typed_command(db, chat_id, SUGGESTIONS_AUTO_SECONDS_KEY, str(clamp_auto_seconds(seconds)), tenant_id=tid)


def set_suggestions_auto_enabled(
    db: Any,
    chat_id: Any,
    enabled: bool,
    *,
    tenant_id: str = "default",
) -> tuple[bool, str]:
    """Persist Auto preference for this chat (DB-Writer when vault is read-only)."""
    tid = str(tenant_id or "default").strip() or "default"
    value = "1" if enabled else "0"
    return set_chat_state_via_typed_command(
        db,
        chat_id,
        SUGGESTIONS_AUTO_KEY,
        value,
        tenant_id=tid,
    )
