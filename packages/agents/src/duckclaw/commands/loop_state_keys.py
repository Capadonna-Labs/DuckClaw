"""agent_config keys for /loop (formerly /meditate) with legacy dual-read."""

from __future__ import annotations

from typing import Any

from duckclaw.commands.chat_state import get_chat_state, set_chat_state, set_chat_state_via_typed_command
from duckclaw.commands.chat_state import _skip_runtime_ddl

LOOP_DELTA_SECONDS_KEY = "loop_delta_seconds"
LOOP_DELTA_IDLE_KEY = "loop_delta_idle"
LOOP_LAST_FIRE_KEY = "loop_last_fire_epoch"
LOOP_LAST_ACTIVITY_KEY = "loop_last_activity_epoch"
LOOP_PENDING_TICK_KEY = "loop_pending_tick"
LOOP_TENANT_KEY = "loop_tenant_id"
LOOP_WORKER_KEY = "loop_worker_id"
LOOP_ACTIVE_KEY = "loop_active"
LOOP_AWAITING_USER_KEY = "loop_awaiting_user"
LOOP_HITL_PENDING_KEY = "loop_hitl_pending"

_LEGACY_TO_LOOP: dict[str, str] = {
    "meditate_delta_seconds": LOOP_DELTA_SECONDS_KEY,
    "meditate_last_fire_epoch": LOOP_LAST_FIRE_KEY,
    "meditate_tenant_id": LOOP_TENANT_KEY,
    "meditate_worker_id": LOOP_WORKER_KEY,
    "meditate_active": LOOP_ACTIVE_KEY,
    "meditate_awaiting_user": LOOP_AWAITING_USER_KEY,
    "meditate_hitl_pending": LOOP_HITL_PENDING_KEY,
}

LOOP_CHAT_STATE_KEYS: tuple[str, ...] = (
    LOOP_DELTA_SECONDS_KEY,
    LOOP_DELTA_IDLE_KEY,
    LOOP_LAST_FIRE_KEY,
    LOOP_LAST_ACTIVITY_KEY,
    LOOP_PENDING_TICK_KEY,
    LOOP_TENANT_KEY,
    LOOP_WORKER_KEY,
    LOOP_ACTIVE_KEY,
    LOOP_AWAITING_USER_KEY,
)


def get_loop_chat_state(db: Any, chat_id: Any, loop_key_suffix: str) -> str:
    """Read loop_* key; fall back to legacy meditate_* if empty."""
    val = (get_chat_state(db, chat_id, loop_key_suffix) or "").strip()
    if val:
        return val
    for legacy, loop_key in _LEGACY_TO_LOOP.items():
        if loop_key == loop_key_suffix:
            return (get_chat_state(db, chat_id, legacy) or "").strip()
    return ""


def persist_loop_chat_state(
    db: Any,
    chat_id: Any,
    key_suffix: str,
    value: str,
    *,
    tenant_id: str = "default",
) -> tuple[bool, str]:
    tid = str(tenant_id or "default").strip() or "default"
    if _skip_runtime_ddl(db):
        return set_chat_state_via_typed_command(
            db,
            chat_id,
            key_suffix,
            value,
            tenant_id=tid,
        )
    set_chat_state(db, chat_id, key_suffix, value)
    return True, ""


def migrate_loop_chat_state_keys(db: Any, chat_id: Any, *, tenant_id: str = "default") -> None:
    """Copy meditate_* → loop_* when loop empty and legacy has value."""
    tid = str(tenant_id or "default").strip() or "default"
    for legacy, loop_key in _LEGACY_TO_LOOP.items():
        current = (get_chat_state(db, chat_id, loop_key) or "").strip()
        if current:
            continue
        legacy_val = (get_chat_state(db, chat_id, legacy) or "").strip()
        if not legacy_val:
            continue
        persist_loop_chat_state(db, chat_id, loop_key, legacy_val, tenant_id=tid)
