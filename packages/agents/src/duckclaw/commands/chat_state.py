"""Chat-scoped runtime state stored in the legacy ``agent_config`` table."""

from __future__ import annotations

import json
from typing import Any

_PREFIX = "chat_"
_AGENT_CONFIG_TABLE = "agent_config"


def _skip_runtime_ddl(db: Any) -> bool:
    """Return True when runtime code must not create or alter DuckDB tables."""
    return bool(getattr(db, "_read_only", False))


def _chat_key(chat_id: Any, suffix: str) -> str:
    """Key for agent_config; supports numeric Telegram IDs and string API session IDs."""
    try:
        cid = int(chat_id)
        return f"{_PREFIX}{cid}_{suffix}"
    except (TypeError, ValueError):
        return f"{_PREFIX}{str(chat_id)[:64]}_{suffix}"


def _ensure_agent_config(db: Any) -> None:
    if _skip_runtime_ddl(db):
        return
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_AGENT_CONFIG_TABLE} (
            key VARCHAR PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def get_chat_state(db: Any, chat_id: Any, key: str) -> str:
    """Read a chat-scoped config key from agent_config."""
    _ensure_agent_config(db)
    k = _chat_key(chat_id, key).replace("'", "''")[:200]
    try:
        result = db.query(f"SELECT value FROM {_AGENT_CONFIG_TABLE} WHERE key = '{k}' LIMIT 1")
        rows = json.loads(result) if isinstance(result, str) else (result or [])
        if rows and isinstance(rows[0], dict):
            return (rows[0].get("value") or "").strip()
    except Exception:
        pass
    return ""


def set_chat_state(db: Any, chat_id: Any, key: str, value: str) -> None:
    """Write a chat-scoped config key to agent_config."""
    _ensure_agent_config(db)
    k = _chat_key(chat_id, key).replace("'", "''")[:128]
    v = str(value).replace("'", "''")[:16384]
    db.execute(
        f"""
        INSERT INTO {_AGENT_CONFIG_TABLE} (key, value) VALUES ('{k}', '{v}')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """
    )


def get_global_config(db: Any, key: str) -> str:
    """Read a global config key from agent_config."""
    _ensure_agent_config(db)
    k = str(key).replace("'", "''")[:128]
    try:
        result = db.query(f"SELECT value FROM {_AGENT_CONFIG_TABLE} WHERE key = '{k}' LIMIT 1")
        rows = json.loads(result) if isinstance(result, str) else (result or [])
        if rows and isinstance(rows[0], dict):
            return (rows[0].get("value") or "").strip()
    except Exception:
        pass
    return ""


def set_global_config(db: Any, key: str, value: str) -> None:
    """Write a global config key to agent_config."""
    _ensure_agent_config(db)
    k = str(key).replace("'", "''")[:128]
    v = str(value).replace("'", "''")[:16384]
    db.execute(
        f"""
        INSERT INTO {_AGENT_CONFIG_TABLE} (key, value) VALUES ('{k}', '{v}')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """
    )


_get_global_config = get_global_config
_set_global_config = set_global_config

