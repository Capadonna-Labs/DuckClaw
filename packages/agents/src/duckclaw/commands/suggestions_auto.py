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
