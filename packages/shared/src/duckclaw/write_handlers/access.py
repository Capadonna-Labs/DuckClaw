"""Team access and shared grant typed write handlers."""
from __future__ import annotations

from typing import Any

from duckclaw.shared_db_grants import validate_resource_key


def _normalize_authorized_user_role(raw: Any) -> str:
    role = str(raw or "user").strip().lower()
    if role not in {"admin", "user"}:
        raise ValueError(f"Invalid authorized user role: {raw}")
    return role


def _apply_upsert_authorized_user(conn: Any, payload: dict) -> None:
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    user_id = str(payload.get("user_id") or "").strip()
    username = str(payload.get("username") or "Usuario").strip() or "Usuario"
    role = _normalize_authorized_user_role(payload.get("role"))
    if not user_id:
        raise ValueError("user_id required")

    conn.execute(
        """
        INSERT INTO main.authorized_users (tenant_id, user_id, username, role)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (tenant_id, user_id) DO UPDATE SET
          username = EXCLUDED.username,
          role = EXCLUDED.role,
          added_at = now()
        """,
        [tenant_id, user_id, username[:128], role],
    )


def _apply_delete_authorized_user(conn: Any, payload: dict) -> None:
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    user_id = str(payload.get("user_id") or "").strip()
    if not user_id:
        raise ValueError("user_id required")

    conn.execute(
        "DELETE FROM main.authorized_users WHERE lower(tenant_id)=lower(?) AND user_id=?",
        [tenant_id, user_id],
    )


def _normalize_shared_resource_key(raw: Any) -> str:
    resource_key = str(raw or "").strip().lower()
    if not resource_key or not validate_resource_key(resource_key):
        raise ValueError("Invalid shared resource_key")
    return resource_key


def _apply_upsert_shared_db_grant(conn: Any, payload: dict) -> None:
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    user_id = str(payload.get("user_id") or "").strip()
    resource_key = _normalize_shared_resource_key(payload.get("resource_key"))
    if not user_id:
        raise ValueError("user_id required")

    conn.execute(
        """
        INSERT INTO main.user_shared_db_access (tenant_id, user_id, resource_key)
        VALUES (?, ?, ?)
        ON CONFLICT (tenant_id, user_id, resource_key) DO UPDATE SET
          created_at = now()
        """,
        [tenant_id, user_id, resource_key],
    )


def _apply_delete_shared_db_grant(conn: Any, payload: dict) -> None:
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    user_id = str(payload.get("user_id") or "").strip()
    resource_key = _normalize_shared_resource_key(payload.get("resource_key"))
    if not user_id:
        raise ValueError("user_id required")

    conn.execute(
        "DELETE FROM main.user_shared_db_access "
        "WHERE tenant_id = ? AND user_id = ? AND resource_key = ?",
        [tenant_id, user_id, resource_key],
    )
