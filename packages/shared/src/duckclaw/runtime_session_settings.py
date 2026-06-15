"""Chat-scoped runtime settings stored in ``admin_runtime_settings``."""

from __future__ import annotations

from typing import Any

RUNTIME_SESSION_DOMAIN = "runtime.session"


def runtime_session_actor(chat_id: Any) -> str:
    """Actor scope used for per-chat runtime settings."""
    raw = str(chat_id or "default").strip() or "default"
    return f"chat:{raw[:128]}"


def resolve_session_runtime_setting(
    db: Any,
    chat_id: Any,
    key: str,
    *,
    tenant_id: str = "default",
    default: str = "",
) -> str:
    """Resolve one per-chat runtime setting, returning ``default`` if unavailable."""
    if db is None:
        return default
    try:
        from duckclaw.admin_runtime_settings import resolve_runtime_setting

        resolved = resolve_runtime_setting(
            db,
            tenant_id=str(tenant_id or "default").strip() or "default",
            actor_email=runtime_session_actor(chat_id),
            domain=RUNTIME_SESSION_DOMAIN,
            key=key,
            default=default,
        )
        return str(resolved.get("value") or "").strip()
    except Exception:
        return default


def upsert_session_runtime_setting(
    db: Any,
    chat_id: Any,
    key: str,
    value: str,
    *,
    tenant_id: str = "default",
    updated_by: str = "system",
) -> None:
    """Persist one per-chat runtime setting in the DB-first control plane."""
    from duckclaw.admin_runtime_settings import upsert_runtime_setting

    upsert_runtime_setting(
        db,
        tenant_id=str(tenant_id or "default").strip() or "default",
        actor_email=runtime_session_actor(chat_id),
        domain=RUNTIME_SESSION_DOMAIN,
        key=key,
        value_text=str(value)[:8192],
        value_kind="boolean",
        updated_by=updated_by,
    )


__all__ = [
    "RUNTIME_SESSION_DOMAIN",
    "resolve_session_runtime_setting",
    "runtime_session_actor",
    "upsert_session_runtime_setting",
]
