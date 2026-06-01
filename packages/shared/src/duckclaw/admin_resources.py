"""Cross-cutting admin resource tables.

These tables support audit/search/policy concerns without owning RBAC decisions.
Typed domain tables remain the source of truth for permissions and ownership.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from duckclaw.shared_db_grants import _query_all_dicts, _sql_lit

_ADMIN_RESOURCE_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_resource_events (
    event_id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL,
    actor_email VARCHAR NOT NULL,
    resource_kind VARCHAR NOT NULL,
    resource_id VARCHAR NOT NULL,
    event_type VARCHAR NOT NULL,
    payload_redacted_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_admin_resource_events_tenant_created
    ON main.admin_resource_events (tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_admin_resource_events_resource
    ON main.admin_resource_events (resource_kind, resource_id);
"""

_ADMIN_RESOURCE_TAGS_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_resource_tags (
    resource_kind VARCHAR NOT NULL,
    resource_id VARCHAR NOT NULL,
    tag VARCHAR NOT NULL,
    created_by VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (resource_kind, resource_id, tag)
);
"""

_ADMIN_SECRET_REFS_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_secret_refs (
    secret_ref VARCHAR PRIMARY KEY,
    owner_email VARCHAR,
    tenant_id VARCHAR NOT NULL,
    provider VARCHAR NOT NULL,
    purpose VARCHAR NOT NULL,
    env_key VARCHAR,
    status VARCHAR DEFAULT 'active',
    rotated_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_SENSITIVE_KEY_PARTS = ("secret", "token", "password", "api_key", "apikey", "key")


def ensure_admin_resource_tables(db: Any) -> None:
    if getattr(db, "_read_only", False):
        return
    for ddl in (_ADMIN_RESOURCE_EVENTS_DDL, _ADMIN_RESOURCE_TAGS_DDL, _ADMIN_SECRET_REFS_DDL):
        for stmt in ddl.strip().split(";"):
            sql = stmt.strip()
            if sql:
                db.execute(sql)


def _redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
                continue
            out[str(key)] = _redact_payload(item)
        return out
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    return value


def record_resource_event(
    db: Any,
    *,
    tenant_id: str,
    actor_email: str,
    resource_kind: str,
    resource_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, str]:
    ensure_admin_resource_tables(db)
    event_id = f"evt_{uuid.uuid4().hex}"
    redacted = json.dumps(_redact_payload(payload or {}), ensure_ascii=False, sort_keys=True)
    db.execute(
        f"""
        INSERT INTO main.admin_resource_events
          (event_id, tenant_id, actor_email, resource_kind, resource_id, event_type, payload_redacted_json)
        VALUES (
          '{_sql_lit(event_id, 64)}',
          '{_sql_lit(tenant_id, 128)}',
          '{_sql_lit(actor_email, 256)}',
          '{_sql_lit(resource_kind, 64)}',
          '{_sql_lit(resource_id, 128)}',
          '{_sql_lit(event_type, 128)}',
          '{_sql_lit(redacted, 8192)}'
        )
        """
    )
    return {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "resource_kind": resource_kind,
        "resource_id": resource_id,
        "event_type": event_type,
        "payload_redacted_json": redacted,
    }


def list_resource_events(db: Any, *, tenant_id: str, limit: int = 100) -> list[dict[str, str]]:
    ensure_admin_resource_tables(db)
    lim = max(1, min(int(limit or 100), 500))
    rows = _query_all_dicts(
        db,
        "SELECT event_id, tenant_id, actor_email, resource_kind, resource_id, event_type, "
        "payload_redacted_json, created_at "
        f"FROM main.admin_resource_events WHERE tenant_id = '{_sql_lit(tenant_id, 128)}' "
        f"ORDER BY created_at DESC, event_id DESC LIMIT {lim}",
    )
    out: list[dict[str, str]] = []
    for row in rows:
        if isinstance(row, dict):
            out.append({key: str(row.get(key) or "") for key in row.keys()})
    return out
