"""Runtime, chat-state and audit typed write handlers."""

from __future__ import annotations

import json
import uuid
from typing import Any


def _apply_upsert_runtime_setting(conn: Any, payload: dict) -> None:
    domain = str(payload["domain"])
    key = str(payload["key"])
    value = str(payload["value"])
    value_json = payload.get("value_json")
    secret = bool(payload.get("secret", False))
    value_kind = "secret" if secret else str(payload.get("value_kind", "string"))
    json_text = json.dumps(value_json, ensure_ascii=False, sort_keys=True) if value_json is not None else ""
    tenant_id = str(payload.get("tenant_id") or "default")
    actor = str(payload.get("actor_email", "system"))
    updated_by = str(payload.get("updated_by") or actor)

    existing = conn.execute(
        "SELECT setting_id FROM main.admin_runtime_settings "
        "WHERE tenant_id = ? AND actor_email = ? AND domain = ? AND key = ?",
        [tenant_id, actor, domain, key],
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE main.admin_runtime_settings "
            "SET value_text = ?, value_json = ?, value_kind = ?, secret = ?, source = 'db', "
            "active = true, updated_by = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE setting_id = ?",
            [value, json_text, value_kind, secret, updated_by, existing[0]],
        )
        return

    setting_id = f"set_{uuid.uuid4().hex[:16]}"
    conn.execute(
        "INSERT INTO main.admin_runtime_settings "
        "(setting_id, tenant_id, actor_email, domain, key, value_text, value_json, "
        "value_kind, secret, source, created_by, updated_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'db', ?, ?)",
        [setting_id, tenant_id, actor, domain, key, value, json_text, value_kind, secret, updated_by, updated_by],
    )


def _ensure_agent_config_table(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_config (
            key VARCHAR PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _apply_upsert_agent_config_entries(conn: Any, payload: dict) -> None:
    entries = payload.get("entries") or {}
    if not isinstance(entries, dict) or not entries:
        raise ValueError("entries required")

    _ensure_agent_config_table(conn)
    for raw_key, raw_value in entries.items():
        key = str(raw_key or "").strip()[:128]
        if not key:
            raise ValueError("agent_config entry key required")
        value = str(raw_value or "")[:16384]
        conn.execute(
            """
            INSERT INTO agent_config (key, value)
            VALUES (?, ?)
            ON CONFLICT (key) DO UPDATE SET
              value = EXCLUDED.value,
              updated_at = now()
            """,
            [key, value],
        )


def _apply_delete_agent_config_entries(conn: Any, payload: dict) -> None:
    raw_keys = payload.get("keys") or []
    if not isinstance(raw_keys, list) or not raw_keys:
        raise ValueError("keys required")

    _ensure_agent_config_table(conn)
    keys = sorted({str(raw_key or "").strip()[:128] for raw_key in raw_keys})
    for key in keys:
        if not key:
            raise ValueError("agent_config entry key required")
        conn.execute("DELETE FROM agent_config WHERE key = ?", [key])


def _chat_agent_config_key(chat_id: Any, suffix: str) -> str:
    try:
        return f"chat_{int(chat_id)}_{suffix}"
    except (TypeError, ValueError):
        return f"chat_{str(chat_id)[:64]}_{suffix}"


def _duckdb_table_exists(conn: Any, table_name: str) -> bool:
    row = conn.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
        [table_name],
    ).fetchone()
    return bool(row and int(row[0] or 0) > 0)


def _apply_forget_chat_state(conn: Any, payload: dict) -> None:
    raw_chat_id = str(payload.get("chat_id") or "").strip()
    if not raw_chat_id:
        raise ValueError("chat_id required")

    try:
        telegram_chat_id = int(raw_chat_id)
        if _duckdb_table_exists(conn, "telegram_conversation"):
            conn.execute(
                "DELETE FROM telegram_conversation WHERE chat_id = ?",
                [telegram_chat_id],
            )
    except (TypeError, ValueError):
        if _duckdb_table_exists(conn, "api_conversation"):
            conn.execute(
                "DELETE FROM api_conversation WHERE session_id = ?",
                [raw_chat_id[:256]],
            )

    _ensure_agent_config_table(conn)
    for suffix in ("last_audit", "context_fold_summary"):
        conn.execute(
            "DELETE FROM agent_config WHERE key = ?",
            [_chat_agent_config_key(raw_chat_id, suffix)[:128]],
        )


_TASK_AUDIT_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS main.task_audit_log (
    task_id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    worker_id VARCHAR,
    query_prefix VARCHAR,
    status VARCHAR NOT NULL,
    duration_ms INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    plan_title VARCHAR
)
"""


def _ensure_task_audit_log_table(conn: Any) -> None:
    conn.execute(_TASK_AUDIT_TABLE_DDL)
    try:
        conn.execute("ALTER TABLE main.task_audit_log ADD COLUMN plan_title VARCHAR")
    except Exception:
        pass


def _normalize_task_audit_status(raw: Any) -> str:
    status = str(raw or "SUCCESS").strip().upper()
    allowed = {"SUCCESS", "FAILED", "PROACTIVE_MESSAGE_SENT", "SECURITY_VIOLATION_ATTEMPT"}
    return status if status in allowed else "SUCCESS"


def _apply_append_task_audit(conn: Any, payload: dict) -> None:
    _ensure_task_audit_log_table(conn)
    audit_task_id = str(payload.get("audit_task_id") or payload.get("task_id") or "").strip()
    if not audit_task_id:
        raise ValueError("audit_task_id required")
    tenant_id = str(payload.get("tenant_id") or "default").strip()[:128] or "default"
    worker_id = str(payload.get("worker_id") or "").strip()[:64]
    query_prefix = str(payload.get("query_prefix") or "")[:256]
    status = _normalize_task_audit_status(payload.get("status"))
    duration_ms = max(0, int(payload.get("duration_ms") or 0))
    plan_title = str(payload.get("plan_title") or "")[:256]
    conn.execute(
        """
        INSERT INTO main.task_audit_log
        (task_id, tenant_id, worker_id, query_prefix, status, duration_ms, plan_title)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (task_id) DO NOTHING
        """,
        [audit_task_id, tenant_id, worker_id, query_prefix, status, duration_ms, plan_title],
    )


from duckclaw.write_handlers.registry import register_handler

register_handler("upsert_runtime_setting", _apply_upsert_runtime_setting)
register_handler("upsert_agent_config_entries", _apply_upsert_agent_config_entries)
register_handler("delete_agent_config_entries", _apply_delete_agent_config_entries)
register_handler("forget_chat_state", _apply_forget_chat_state)
register_handler("append_task_audit", _apply_append_task_audit)

