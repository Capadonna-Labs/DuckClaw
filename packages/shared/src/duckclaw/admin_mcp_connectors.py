"""DB-first MCP connector registry (read paths)."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from duckclaw.admin_runtime_settings import resolve_runtime_setting


def _fetchall(result: Any) -> list[Any]:
    if hasattr(result, "fetchall"):
        return list(result.fetchall())
    if isinstance(result, list):
        return result
    return []


def _fetchone(result: Any) -> Any | None:
    if hasattr(result, "fetchone"):
        return result.fetchone()
    rows = _fetchall(result)
    return rows[0] if rows else None


def ensure_admin_mcp_connectors_schema(db: Any) -> None:
    """DDL/migrations only on writable handles; gateway admin routes use read_only=True."""
    if getattr(db, "_read_only", False):
        return
    from duckclaw.schema_migrations import run_pending_migrations

    run_pending_migrations(db)


def _row_to_connector(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        data = row
    else:
        cols = [
            "connector_id",
            "tenant_id",
            "owner_email",
            "display_name",
            "transport",
            "endpoint_url",
            "launch_command",
            "launch_args_json",
            "launch_env_json",
            "auth_kind",
            "auth_secret_key",
            "tool_allowlist_json",
            "tool_denylist_json",
            "read_only",
            "egress_hosts_json",
            "preset_id",
            "enabled",
            "active",
            "metadata_json",
            "created_at",
            "updated_at",
        ]
        data = dict(zip(cols, row))
    allowlist = _json_list(data.get("tool_allowlist_json"))
    denylist = _json_list(data.get("tool_denylist_json"))
    egress = _json_list(data.get("egress_hosts_json"))
    return {
        "connector_id": str(data.get("connector_id") or ""),
        "tenant_id": str(data.get("tenant_id") or "default"),
        "owner_email": str(data.get("owner_email") or ""),
        "display_name": str(data.get("display_name") or ""),
        "transport": str(data.get("transport") or ""),
        "endpoint_url": str(data.get("endpoint_url") or ""),
        "launch_command": str(data.get("launch_command") or ""),
        "launch_args": _json_list(data.get("launch_args_json")),
        "launch_env": _json_dict(data.get("launch_env_json")),
        "auth_kind": str(data.get("auth_kind") or "none"),
        "auth_secret_key": str(data.get("auth_secret_key") or ""),
        "tool_allowlist": allowlist,
        "tool_denylist": denylist,
        "read_only": bool(data.get("read_only", True)),
        "egress_hosts": egress,
        "preset_id": str(data.get("preset_id") or ""),
        "enabled": bool(data.get("enabled", True)),
        "active": bool(data.get("active", True)),
        "metadata": _json_dict(data.get("metadata_json")),
        "created_at": str(data.get("created_at") or ""),
        "updated_at": str(data.get("updated_at") or ""),
    }


def _json_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(x) for x in parsed if str(x).strip()]
    except json.JSONDecodeError:
        pass
    return []


def _json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {}


def list_mcp_connectors(db: Any, *, tenant_id: str = "default", include_inactive: bool = False) -> list[dict[str, Any]]:
    ensure_admin_mcp_connectors_schema(db)
    sql = (
        "SELECT connector_id, tenant_id, owner_email, display_name, transport, endpoint_url, "
        "launch_command, launch_args_json, launch_env_json, auth_kind, auth_secret_key, "
        "tool_allowlist_json, tool_denylist_json, read_only, egress_hosts_json, preset_id, "
        "enabled, active, metadata_json, created_at, updated_at "
        "FROM main.admin_mcp_connectors WHERE tenant_id = ? "
    )
    params: list[Any] = [tenant_id]
    if not include_inactive:
        sql += "AND active = true "
    sql += "ORDER BY display_name, connector_id"
    rows = _fetchall(db.execute(sql, params))
    out: list[dict[str, Any]] = []
    for row in rows:
        connector = _row_to_connector(row)
        connector["has_auth"] = _connector_has_auth(db, connector)
        connector.pop("auth_secret_key", None)
        out.append(connector)
    return out


def get_mcp_connector(db: Any, *, connector_id: str, tenant_id: str = "default") -> dict[str, Any] | None:
    ensure_admin_mcp_connectors_schema(db)
    row = _fetchone(
        db.execute(
            "SELECT connector_id, tenant_id, owner_email, display_name, transport, endpoint_url, "
            "launch_command, launch_args_json, launch_env_json, auth_kind, auth_secret_key, "
            "tool_allowlist_json, tool_denylist_json, read_only, egress_hosts_json, preset_id, "
            "enabled, active, metadata_json, created_at, updated_at "
            "FROM main.admin_mcp_connectors WHERE connector_id = ? AND tenant_id = ? LIMIT 1",
            [connector_id, tenant_id],
        )
    )
    if not row:
        return None
    connector = _row_to_connector(row)
    connector["has_auth"] = _connector_has_auth(db, connector)
    connector.pop("auth_secret_key", None)
    return connector


def get_mcp_connector_runtime(db: Any, *, connector_id: str, tenant_id: str = "default") -> dict[str, Any] | None:
    """Includes auth_secret_key for runtime (not for API responses)."""
    ensure_admin_mcp_connectors_schema(db)
    row = _fetchone(
        db.execute(
            "SELECT connector_id, tenant_id, owner_email, display_name, transport, endpoint_url, "
            "launch_command, launch_args_json, launch_env_json, auth_kind, auth_secret_key, "
            "tool_allowlist_json, tool_denylist_json, read_only, egress_hosts_json, preset_id, "
            "enabled, active, metadata_json, created_at, updated_at "
            "FROM main.admin_mcp_connectors WHERE connector_id = ? AND tenant_id = ? AND active = true AND enabled = true LIMIT 1",
            [connector_id, tenant_id],
        )
    )
    if not row:
        return None
    return _row_to_connector(row)


def _connector_has_auth(db: Any, connector: dict[str, Any]) -> bool:
    kind = str(connector.get("auth_kind") or "none").strip().lower()
    preset = str(connector.get("preset_id") or "").strip().lower()
    from duckclaw.mcp_connector_presets import preset_supports_oauth_pkce, resolve_preset_id

    if resolve_preset_id(preset) == "spotify":
        from duckclaw.mcp_spotify_oauth import spotify_mcp_config_authenticated

        return spotify_mcp_config_authenticated()

    if preset_supports_oauth_pkce(preset) and kind in ("", "none"):
        kind = "bearer"
    if kind in ("", "none"):
        return True
    if kind == "bearer":
        token = resolve_connector_bearer_token(db, connector)
        return bool(token)
    return False


def resolve_connector_bearer_token(db: Any, connector: dict[str, Any]) -> str:
    kind = str(connector.get("auth_kind") or "none").strip().lower()
    if kind in ("", "none"):
        return ""
    secret_key = str(connector.get("auth_secret_key") or "").strip()
    if not secret_key:
        return ""
    tenant_id = str(connector.get("tenant_id") or "default")
    owner = str(connector.get("owner_email") or "system").strip().lower()
    token = ""
    updated_at = None
    for actor in (owner, ""):
        resolved = resolve_runtime_setting(
            db,
            tenant_id=tenant_id,
            actor_email=actor,
            domain="mcp_connector",
            key=secret_key,
        )
        token = str(resolved.get("value") or "").strip()
        if token:
            break
    if not token:
        # ponytail: OAuth guarda bearer bajo actor de sesión, no owner_email del conector.
        row = _fetchone(
            db.execute(
                "SELECT value_text, updated_at FROM main.admin_runtime_settings "
                "WHERE active = true AND domain = 'mcp_connector' AND key = ? AND tenant_id = ? "
                "AND secret = true AND length(trim(coalesce(value_text, ''))) > 0 "
                "ORDER BY updated_at DESC LIMIT 1",
                [secret_key, tenant_id],
            )
        )
        if row:
            if isinstance(row, dict):
                token = str(row.get("value_text") or "").strip()
                updated_at = row.get("updated_at")
            else:
                token = str(row[0] or "").strip()
                updated_at = row[1] if len(row) > 1 else None

    preset_id = str(connector.get("preset_id") or "").strip()
    from duckclaw.mcp_connector_presets import is_google_workspace_preset

    if not is_google_workspace_preset(preset_id):
        return token

    connector_id = str(connector.get("connector_id") or "").strip()
    refresh_key = f"{connector_id}.refresh" if connector_id else ""
    refresh = ""
    if refresh_key:
        for actor in (owner, ""):
            resolved = resolve_runtime_setting(
                db,
                tenant_id=tenant_id,
                actor_email=actor,
                domain="mcp_connector",
                key=refresh_key,
            )
            refresh = str(resolved.get("value") or "").strip()
            if refresh:
                break
        if not refresh:
            row = _fetchone(
                db.execute(
                    "SELECT value_text FROM main.admin_runtime_settings "
                    "WHERE active = true AND domain = 'mcp_connector' AND key = ? AND tenant_id = ? "
                    "AND secret = true AND length(trim(coalesce(value_text, ''))) > 0 "
                    "ORDER BY updated_at DESC LIMIT 1",
                    [refresh_key, tenant_id],
                )
            )
            if row:
                refresh = str(row[0] if not isinstance(row, dict) else row.get("value_text") or "").strip()

    if not refresh:
        return token

    # ponytail: Google access tokens ~1h; refresh if missing/stale without tokeninfo roundtrip.
    stale = True
    if token and updated_at is not None:
        try:
            from datetime import datetime, timezone

            ts = updated_at
            if hasattr(ts, "tzinfo") and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_s = (datetime.now(timezone.utc) - ts).total_seconds()
            stale = age_s > 3000
        except Exception:
            stale = True
    elif not token:
        stale = True
    else:
        # updated_at unknown — verify with tokeninfo once
        try:
            import httpx

            info = httpx.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"access_token": token},
                timeout=8.0,
            )
            stale = info.status_code >= 400
        except Exception:
            stale = True

    if not stale:
        return token

    try:
        from duckclaw.mcp_google_workspace_oauth import refresh_google_access_token

        fresh = refresh_google_access_token(refresh)
    except Exception:
        return token
    if not fresh:
        return token
    if not getattr(db, "_read_only", False):
        try:
            from duckclaw.write_handlers.mcp_connectors import _apply_set_mcp_connector_auth

            _apply_set_mcp_connector_auth(
                db,
                {
                    "tenant_id": tenant_id,
                    "actor_email": owner or "system",
                    "connector_id": connector_id,
                    "bearer_token": fresh,
                },
            )
        except Exception:
            pass
    return fresh


def list_worker_mcp_connectors(
    db: Any,
    *,
    worker_uid: str,
    tenant_id: str = "default",
) -> list[dict[str, Any]]:
    ensure_admin_mcp_connectors_schema(db)
    rows = _fetchall(
        db.execute(
            """
            SELECT c.connector_id, c.tenant_id, c.owner_email, c.display_name, c.transport, c.endpoint_url,
                   c.launch_command, c.launch_args_json, c.launch_env_json, c.auth_kind, c.auth_secret_key,
                   c.tool_allowlist_json, c.tool_denylist_json, c.read_only, c.egress_hosts_json, c.preset_id,
                   c.enabled, c.active, c.metadata_json, c.created_at, c.updated_at
            FROM main.admin_worker_mcp_grants g
            JOIN main.admin_mcp_connectors c ON c.connector_id = g.connector_id
            WHERE g.worker_uid = ?
              AND g.active = true
              AND c.tenant_id = ?
              AND c.active = true
              AND c.enabled = true
            ORDER BY c.display_name
            """,
            [worker_uid, tenant_id],
        )
    )
    return [_row_to_connector(row) for row in rows]


def resolve_worker_uid(db: Any, *, worker_id: str, tenant_id: str = "default") -> str | None:
    row = _fetchone(
        db.execute(
            "SELECT worker_uid FROM main.admin_worker_catalog "
            "WHERE worker_id = ? AND tenant_id = ? AND active = true LIMIT 1",
            [worker_id, tenant_id],
        )
    )
    if not row:
        return None
    return str(row[0] if not isinstance(row, dict) else row.get("worker_uid") or "")


def validate_connector_egress(connector: dict[str, Any]) -> None:
    transport = str(connector.get("transport") or "").strip().lower()
    if transport != "streamable_http":
        return
    url = str(connector.get("endpoint_url") or "").strip()
    if not url:
        raise ValueError("endpoint_url required for streamable_http")
    host = (urlparse(url).hostname or "").strip().lower()
    if not host:
        raise ValueError("invalid endpoint_url host")
    allowed = {h.strip().lower() for h in connector.get("egress_hosts") or [] if str(h).strip()}
    if allowed and host not in allowed:
        raise ValueError(f"egress host not allowed: {host}")


def tool_allowed_by_policy(connector: dict[str, Any], tool_name: str) -> bool:
    name = str(tool_name or "").strip()
    if not name:
        return False
    denylist = {str(x).strip().lower() for x in connector.get("tool_denylist") or [] if str(x).strip()}
    if name.lower() in denylist:
        return False
    allowlist = [str(x).strip() for x in connector.get("tool_allowlist") or [] if str(x).strip()]
    if not allowlist:
        allowed = True
    elif "*" in allowlist:
        allowed = True
    else:
        allowed = name in allowlist
    if not allowed:
        return False
    if not connector.get("read_only", True):
        return True
    lower = name.lower()
    mutating_prefixes = ("create_", "delete_", "update_", "push_", "write_", "remove_", "merge_")
    if lower.startswith(mutating_prefixes):
        return False
    return True
