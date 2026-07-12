"""DB-first runtime settings for DuckClaw Admin.

Spec: specs/features/platform/ADMIN_RUNTIME_SETTINGS.md
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

from duckclaw.shared_db_grants import _query_all_dicts, _sql_lit

_SETTING_ID_PREFIX = "set_"
_NAME_RE = re.compile(r"[^a-z0-9_.-]+")
_MASKED_SECRET = "********"

_ADMIN_RUNTIME_SETTINGS_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_runtime_settings (
    setting_id VARCHAR PRIMARY KEY,
    tenant_id VARCHAR NOT NULL DEFAULT 'global',
    actor_email VARCHAR NOT NULL DEFAULT '',
    domain VARCHAR NOT NULL,
    key VARCHAR NOT NULL,
    value_text TEXT,
    value_json TEXT,
    value_kind VARCHAR NOT NULL DEFAULT 'string',
    secret BOOLEAN DEFAULT false,
    source VARCHAR NOT NULL DEFAULT 'db',
    active BOOLEAN DEFAULT true,
    created_by VARCHAR,
    updated_by VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, actor_email, domain, key)
);
CREATE INDEX IF NOT EXISTS idx_admin_runtime_settings_lookup
    ON main.admin_runtime_settings (tenant_id, actor_email, domain, key, active);
"""

_FALLBACKS: dict[tuple[str, str], dict[str, str]] = {
    ("duckdb", "legacy_schemas"): {
        "env_key": "DUCKCLAW_ADMIN_DUCKDB_LEGACY_SCHEMAS",
        "default": "",
    },
    ("duckdb", "legacy_main_tables"): {
        "env_key": "DUCKCLAW_ADMIN_DUCKDB_LEGACY_MAIN_TABLES",
        "default": "",
    },
    ("telegram", "webhook_routes"): {
        "env_key": "DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES",
        "default": "",
    },
    ("mcp", "port"): {
        "env_key": "DUCKCLAW_MCP_PORT",
        "default": "8001",
    },
    ("comfyui", "api_url"): {
        "env_key": "COMFYUI_API_URL",
        "default": "http://127.0.0.1:8188",
    },
    ("comfyui", "timeout_sec"): {
        "env_key": "COMFYUI_TIMEOUT_SEC",
        "default": "300",
    },
}


def _merged_fallbacks() -> dict[tuple[str, str], dict[str, Any]]:
    merged: dict[tuple[str, str], dict[str, Any]] = dict(_FALLBACKS)
    try:
        from duckclaw.integration_catalog import integration_setting_fallbacks

        merged.update(integration_setting_fallbacks())
    except Exception:
        pass
    return merged


def ensure_admin_runtime_settings_table(db: Any) -> None:
    if getattr(db, "_read_only", False):
        return
    for stmt in _ADMIN_RUNTIME_SETTINGS_DDL.strip().split(";"):
        sql = stmt.strip()
        if sql:
            db.execute(sql)


def normalize_runtime_setting_name(value: str) -> str:
    normalized = _NAME_RE.sub("_", (value or "").strip().lower()).strip("_.-")
    if not normalized:
        raise ValueError("Nombre de setting requerido")
    return normalized[:96]


def _normalize_actor(actor_email: str | None) -> str:
    return (actor_email or "").strip().lower()


def _normalize_tenant(tenant_id: str | None) -> str:
    return (tenant_id or "global").strip() or "global"


def _row_value(row: dict[str, Any]) -> Any:
    kind = str(row.get("value_kind") or "string")
    if kind == "json":
        raw = str(row.get("value_json") or "null")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return str(row.get("value_text") or "")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "t", "yes", "y"}


def _public_setting(row: dict[str, Any], *, value: Any, source: str) -> dict[str, Any]:
    secret = _as_bool(row.get("secret", False))
    out: dict[str, Any] = {
        "setting_id": str(row.get("setting_id") or ""),
        "tenant_id": str(row.get("tenant_id") or ""),
        "actor_email": str(row.get("actor_email") or ""),
        "domain": str(row.get("domain") or ""),
        "key": str(row.get("key") or ""),
        "value_kind": str(row.get("value_kind") or "string"),
        "secret": secret,
        "source": source,
        "configured": value not in (None, ""),
        "updated_at": str(row.get("updated_at") or ""),
    }
    if secret:
        out["masked_value"] = _MASKED_SECRET if out["configured"] else ""
    elif out["value_kind"] == "json":
        out["value_json"] = value
    else:
        out["value_text"] = "" if value is None else str(value)
    return out


def _fallback_row(
    domain: str,
    key: str,
    *,
    env_key: str,
    default: str,
    secret: bool = False,
) -> dict[str, Any]:
    value = (os.environ.get(env_key) or default or "").strip()
    return {
        "setting_id": "",
        "tenant_id": "global",
        "actor_email": "",
        "domain": domain,
        "key": key,
        "value_text": value,
        "value_kind": "string",
        "secret": secret,
        "source": "env" if os.environ.get(env_key) is not None else "default",
    }


def _candidate_rows(
    db: Any,
    *,
    tenant_id: str,
    actor_email: str,
    domain: str,
    key: str,
) -> list[dict[str, Any]]:
    tenant = _sql_lit(_normalize_tenant(tenant_id), 128)
    actor = _sql_lit(_normalize_actor(actor_email), 256)
    dom = _sql_lit(normalize_runtime_setting_name(domain), 64)
    setting_key = _sql_lit(normalize_runtime_setting_name(key), 96)
    return _query_all_dicts(
        db,
        "SELECT setting_id, tenant_id, actor_email, domain, key, value_text, value_json, "
        "value_kind, secret, source, active, updated_at "
        "FROM main.admin_runtime_settings "
        "WHERE active = true "
        f"AND domain = '{dom}' AND key = '{setting_key}' "
        f"AND tenant_id IN ('{tenant}', 'global') "
        f"AND actor_email IN ('{actor}', '')",
    )


def _scope_rank(row: dict[str, Any], *, tenant_id: str, actor_email: str) -> int:
    tenant = _normalize_tenant(tenant_id)
    actor = _normalize_actor(actor_email)
    row_tenant = str(row.get("tenant_id") or "")
    row_actor = str(row.get("actor_email") or "")
    if row_tenant == tenant and row_actor == actor:
        return 0
    if row_tenant == tenant and row_actor == "":
        return 1
    if row_tenant == "global" and row_actor == "":
        return 2
    return 99


def resolve_runtime_setting(
    db: Any,
    *,
    tenant_id: str,
    actor_email: str,
    domain: str,
    key: str,
    env_key: str | None = None,
    default: str = "",
) -> dict[str, Any]:
    ensure_admin_runtime_settings_table(db)
    dom = normalize_runtime_setting_name(domain)
    setting_key = normalize_runtime_setting_name(key)
    candidates = sorted(
        _candidate_rows(db, tenant_id=tenant_id, actor_email=actor_email, domain=dom, key=setting_key),
        key=lambda row: _scope_rank(row, tenant_id=tenant_id, actor_email=actor_email),
    )
    if candidates:
        row = candidates[0]
        value = _row_value(row)
        return {**_public_setting(row, value=value, source="db"), "value": value}

    if dom == "integrations":
        from duckclaw.integration_secrets import (
            _env_candidates,
            _resolve_from_db,
            _resolve_from_env,
            integration_spec_for_setting_key,
        )
        spec = integration_spec_for_setting_key(setting_key)
        if spec is not None:
            db_val = _resolve_from_db(db, spec=spec, tenant_id=tenant_id, actor_email=actor_email)
            env_val = _resolve_from_env(_env_candidates(None, spec.env_keys))
            value = db_val or env_val
            source = "db" if db_val else ("env" if env_val else "default")
            row = {
                "setting_id": "",
                "tenant_id": tenant_id,
                "actor_email": actor_email,
                "domain": dom,
                "key": setting_key,
                "value_kind": "string",
                "secret": True,
                "updated_at": "",
            }
            return {**_public_setting(row, value=value, source=source), "value": value}

    fallback_meta = _merged_fallbacks().get((dom, setting_key), {})
    fallback = _fallback_row(
        dom,
        setting_key,
        env_key=env_key or fallback_meta.get("env_key", ""),
        default=default or fallback_meta.get("default", ""),
        secret=bool(fallback_meta.get("secret", False)),
    )
    value = _row_value(fallback)
    return {**_public_setting(fallback, value=value, source=str(fallback["source"])), "value": value}


def list_runtime_settings_effective(
    db: Any,
    *,
    tenant_id: str,
    actor_email: str,
    domains: list[str] | None = None,
) -> list[dict[str, Any]]:
    ensure_admin_runtime_settings_table(db)
    normalized_domains = {normalize_runtime_setting_name(item) for item in (domains or []) if item}
    where_domain = ""
    if normalized_domains:
        quoted = ", ".join(f"'{_sql_lit(item, 64)}'" for item in sorted(normalized_domains))
        where_domain = f"AND domain IN ({quoted}) "
    tenant = _sql_lit(_normalize_tenant(tenant_id), 128)
    actor = _sql_lit(_normalize_actor(actor_email), 256)
    rows = _query_all_dicts(
        db,
        "SELECT setting_id, tenant_id, actor_email, domain, key, value_text, value_json, "
        "value_kind, secret, source, active, updated_at "
        "FROM main.admin_runtime_settings "
        "WHERE active = true "
        f"{where_domain}"
        f"AND tenant_id IN ('{tenant}', 'global') "
        f"AND actor_email IN ('{actor}', '')",
    )
    keys = {(str(row.get("domain") or ""), str(row.get("key") or "")) for row in rows}
    for domain, key in _merged_fallbacks():
        if normalized_domains and domain not in normalized_domains:
            continue
        keys.add((domain, key))
    out: list[dict[str, Any]] = []
    for domain, key in sorted(keys):
        fallback = _merged_fallbacks().get((domain, key), {})
        item = resolve_runtime_setting(
            db,
            tenant_id=tenant_id,
            actor_email=actor_email,
            domain=domain,
            key=key,
            env_key=fallback.get("env_key"),
            default=fallback.get("default", ""),
        )
        item.pop("value", None)
        out.append(item)
    return out


def upsert_runtime_setting(
    db: Any,
    *,
    tenant_id: str,
    actor_email: str,
    domain: str,
    key: str,
    value_text: str = "",
    value_json: Any = None,
    value_kind: str = "string",
    secret: bool = False,
    updated_by: str = "",
) -> dict[str, Any]:
    ensure_admin_runtime_settings_table(db)
    tenant = _normalize_tenant(tenant_id)
    actor = _normalize_actor(actor_email)
    dom = normalize_runtime_setting_name(domain)
    setting_key = normalize_runtime_setting_name(key)
    kind = "secret" if secret else normalize_runtime_setting_name(value_kind or "string")
    json_text = json.dumps(value_json, ensure_ascii=False, sort_keys=True) if value_json is not None else ""
    existing = _query_all_dicts(
        db,
        "SELECT setting_id FROM main.admin_runtime_settings "
        f"WHERE tenant_id = '{_sql_lit(tenant, 128)}' "
        f"AND actor_email = '{_sql_lit(actor, 256)}' "
        f"AND domain = '{_sql_lit(dom, 64)}' "
        f"AND key = '{_sql_lit(setting_key, 96)}' LIMIT 1",
    )
    if existing:
        setting_id = str(existing[0].get("setting_id") or "")
        db.execute(
            f"""
            UPDATE main.admin_runtime_settings
            SET value_text = '{_sql_lit(value_text, 8192)}',
                value_json = '{_sql_lit(json_text, 65535)}',
                value_kind = '{_sql_lit(kind, 32)}',
                secret = {str(bool(secret)).lower()},
                source = 'db',
                active = true,
                updated_by = '{_sql_lit(updated_by, 256)}',
                updated_at = CURRENT_TIMESTAMP
            WHERE setting_id = '{_sql_lit(setting_id, 64)}'
            """
        )
    else:
        setting_id = f"{_SETTING_ID_PREFIX}{uuid.uuid4().hex}"
        db.execute(
            f"""
            INSERT INTO main.admin_runtime_settings
              (setting_id, tenant_id, actor_email, domain, key, value_text, value_json,
               value_kind, secret, source, created_by, updated_by)
            VALUES (
              '{_sql_lit(setting_id, 64)}',
              '{_sql_lit(tenant, 128)}',
              '{_sql_lit(actor, 256)}',
              '{_sql_lit(dom, 64)}',
              '{_sql_lit(setting_key, 96)}',
              '{_sql_lit(value_text, 8192)}',
              '{_sql_lit(json_text, 65535)}',
              '{_sql_lit(kind, 32)}',
              {str(bool(secret)).lower()},
              'db',
              '{_sql_lit(updated_by, 256)}',
              '{_sql_lit(updated_by, 256)}'
            )
            """
        )
    return resolve_runtime_setting(
        db,
        tenant_id=tenant,
        actor_email=actor,
        domain=dom,
        key=setting_key,
    )
