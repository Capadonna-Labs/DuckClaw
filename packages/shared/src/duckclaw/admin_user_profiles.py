"""Admin console operational profiles: tenant, Telegram and channels per login user.

Spec: specs/features/platform/ADMIN_USER_AGENT_WORKSPACES.md
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from duckclaw.storage.shared_db_grants import _query_all_dicts, _sql_lit

_DEFAULT_WORKER_ID = "default"

_ADMIN_USER_PROFILES_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_user_profiles (
    email VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL UNIQUE,
    telegram_user_id VARCHAR,
    channels_json TEXT,
    default_worker_id VARCHAR DEFAULT 'default',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def normalize_profile_email(email: str) -> str:
    return (email or "").strip().lower()


def tenant_id_for_email(email: str) -> str:
    normalized = normalize_profile_email(email)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    local = re.sub(r"[^a-z0-9]+", "-", normalized.split("@", 1)[0]).strip("-")[:24]
    return f"user-{local or 'admin'}-{digest}"


def ensure_admin_user_profiles_table(db: Any) -> None:
    if getattr(db, "_read_only", False):
        return
    db.execute(_ADMIN_USER_PROFILES_DDL)


def _row_to_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "email": str(row.get("email") or ""),
        "tenant_id": str(row.get("tenant_id") or ""),
        "telegram_user_id": str(row.get("telegram_user_id") or ""),
        "channels_json": str(row.get("channels_json") or "{}"),
        "default_worker_id": str(row.get("default_worker_id") or _DEFAULT_WORKER_ID),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def get_profile_by_email(db: Any, email: str) -> dict[str, Any] | None:
    em = _sql_lit(normalize_profile_email(email), 256)
    try:
        rows = _query_all_dicts(
            db,
            "SELECT email, tenant_id, telegram_user_id, channels_json, default_worker_id, "
            "created_at, updated_at "
            f"FROM main.admin_user_profiles WHERE email = '{em}' LIMIT 1",
        )
    except Exception:
        return None
    if not rows or not isinstance(rows[0], dict):
        return None
    return _row_to_public(dict(rows[0]))


def ensure_profile_for_user(
    db: Any,
    *,
    email: str,
    telegram_user_id: str | None = None,
    channels: dict[str, Any] | None = None,
    default_worker_id: str | None = None,
) -> dict[str, Any]:
    ensure_admin_user_profiles_table(db)
    em = normalize_profile_email(email)
    if not em:
        raise ValueError("email requerido")
    existing = get_profile_by_email(db, em)
    if existing:
        return existing

    tenant_id = tenant_id_for_email(em)
    channels_json = json.dumps(channels or {}, ensure_ascii=False)
    worker_id = (default_worker_id or _DEFAULT_WORKER_ID).strip() or _DEFAULT_WORKER_ID
    db.execute(
        f"""
        INSERT INTO main.admin_user_profiles
          (email, tenant_id, telegram_user_id, channels_json, default_worker_id)
        VALUES (
          '{_sql_lit(em, 256)}',
          '{_sql_lit(tenant_id, 128)}',
          '{_sql_lit((telegram_user_id or '').strip(), 64)}',
          '{_sql_lit(channels_json, 4096)}',
          '{_sql_lit(worker_id, 64)}'
        )
        """
    )
    profile = get_profile_by_email(db, em)
    if not profile:
        raise RuntimeError("profile insert failed")
    return profile


def update_profile(
    db: Any,
    *,
    email: str,
    telegram_user_id: str | None = None,
    channels: dict[str, Any] | None = None,
    default_worker_id: str | None = None,
) -> dict[str, Any]:
    profile = ensure_profile_for_user(db, email=email)
    em = _sql_lit(profile["email"], 256)
    clauses: list[str] = ["updated_at = CURRENT_TIMESTAMP"]
    if telegram_user_id is not None:
        clauses.append(f"telegram_user_id = '{_sql_lit(telegram_user_id.strip(), 64)}'")
    if channels is not None:
        clauses.append(f"channels_json = '{_sql_lit(json.dumps(channels, ensure_ascii=False), 4096)}'")
    if default_worker_id is not None:
        worker_id = default_worker_id.strip() or _DEFAULT_WORKER_ID
        clauses.append(f"default_worker_id = '{_sql_lit(worker_id, 64)}'")
    db.execute(
        f"""
        UPDATE main.admin_user_profiles
        SET {', '.join(clauses)}
        WHERE email = '{em}'
        """
    )
    updated = get_profile_by_email(db, profile["email"])
    if not updated:
        raise RuntimeError("profile update failed")
    return updated
