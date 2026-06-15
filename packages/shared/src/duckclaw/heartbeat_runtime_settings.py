"""DB-first heartbeat state for chat sessions."""

from __future__ import annotations

from typing import Any

from duckclaw.admin_runtime_settings import resolve_runtime_setting, upsert_runtime_setting
from duckclaw.runtime_session_settings import runtime_session_actor

HEARTBEAT_RUNTIME_DOMAIN = "runtime.heartbeat"
HEARTBEAT_RUNTIME_KEY = "enabled"
_MISSING = "__duckclaw_heartbeat_missing__"


def parse_heartbeat_enabled_value(value: Any) -> bool | None:
    raw = str(value or "").strip().lower()
    if raw in ("on", "1", "true", "t", "yes", "y", "sí", "si"):
        return True
    if raw in ("off", "0", "false", "f", "no", "n"):
        return False
    return None


def resolve_heartbeat_runtime_state(
    db: Any,
    *,
    tenant_id: str,
    chat_id: Any,
) -> bool | None:
    """Return DB-first heartbeat state, or None when unset/unavailable."""

    if db is None:
        return None
    try:
        resolved = resolve_runtime_setting(
            db,
            tenant_id=str(tenant_id or "default").strip() or "default",
            actor_email=runtime_session_actor(chat_id),
            domain=HEARTBEAT_RUNTIME_DOMAIN,
            key=HEARTBEAT_RUNTIME_KEY,
            default=_MISSING,
        )
    except Exception:
        return None
    value = str(resolved.get("value") or "").strip()
    if value == _MISSING:
        return None
    return parse_heartbeat_enabled_value(value)


def upsert_heartbeat_runtime_state(
    db: Any,
    *,
    tenant_id: str,
    chat_id: Any,
    enabled: bool,
    updated_by: str = "heartbeat",
) -> None:
    """Persist heartbeat state in the DB-first control plane."""

    upsert_runtime_setting(
        db,
        tenant_id=str(tenant_id or "default").strip() or "default",
        actor_email=runtime_session_actor(chat_id),
        domain=HEARTBEAT_RUNTIME_DOMAIN,
        key=HEARTBEAT_RUNTIME_KEY,
        value_text="on" if enabled else "off",
        value_kind="boolean",
        updated_by=updated_by,
    )
