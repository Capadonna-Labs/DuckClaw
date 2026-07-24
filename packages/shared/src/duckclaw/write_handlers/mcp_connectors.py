"""MCP connector registry write handlers."""

from __future__ import annotations

import json
import uuid
from typing import Any

from duckclaw.admin_mcp_connectors import validate_connector_egress
from duckclaw.mcp_connector_presets import preset_payload


def _stable_json(value: Any) -> str:
    return json.dumps(value or [], ensure_ascii=False, sort_keys=True)


def _auth_secret_key(connector_id: str) -> str:
    return f"{connector_id}.bearer"


def _apply_upsert_mcp_connector(conn: Any, payload: dict) -> None:
    tenant_id = str(payload.get("tenant_id") or "default")
    actor = str(payload.get("actor_email") or "system").strip().lower()
    connector_id = str(payload.get("connector_id") or "").strip()
    preset_id = str(payload.get("preset_id") or "").strip().lower()
    from duckclaw.mcp_connector_presets import resolve_preset_id

    preset_id = resolve_preset_id(preset_id)
    preset = preset_payload(preset_id) if preset_id else None
    if not connector_id and preset_id:
        connector_id = f"mcp_{preset_id}"
    if not connector_id:
        connector_id = f"mcp_{uuid.uuid4().hex[:12]}"

    display_name = str(payload.get("display_name") or (preset or {}).get("display_name") or connector_id).strip()
    transport = str(payload.get("transport") or (preset or {}).get("transport") or "").strip().lower()
    if transport not in {"stdio", "streamable_http"}:
        raise ValueError(f"invalid transport: {transport}")

    endpoint_url = str(payload.get("endpoint_url") or (preset or {}).get("endpoint_url") or "").strip()
    launch_command = str(payload.get("launch_command") or (preset or {}).get("launch_command") or "").strip()
    launch_args = payload.get("launch_args")
    if launch_args is None and preset:
        launch_args = preset.get("launch_args") or []
    elif isinstance(launch_args, list) and not launch_args and preset:
        # CreateBody defaults launch_args=[] — empty must not block preset merge.
        launch_args = preset.get("launch_args") or []
    launch_env = payload.get("launch_env")
    if launch_env is None and preset:
        launch_env = preset.get("launch_env") or {}
    elif isinstance(launch_env, dict) and not launch_env and preset:
        launch_env = preset.get("launch_env") or {}

    auth_kind = str(payload.get("auth_kind") or "").strip().lower()
    if auth_kind in ("", "none") and preset:
        auth_kind = str(preset.get("auth_kind") or "none").strip().lower()
    elif not auth_kind:
        auth_kind = str((preset or {}).get("auth_kind") or "none").strip().lower()
    tool_allowlist = payload.get("tool_allowlist")
    if tool_allowlist is None and preset:
        tool_allowlist = preset.get("tool_allowlist") or []
    elif isinstance(tool_allowlist, list) and not tool_allowlist and preset:
        tool_allowlist = preset.get("tool_allowlist") or []
    tool_denylist = payload.get("tool_denylist")
    if tool_denylist is None and preset:
        tool_denylist = preset.get("tool_denylist") or []
    read_only = payload.get("read_only")
    if read_only is None and preset is not None:
        read_only = bool(preset.get("read_only", True))
    if read_only is None:
        read_only = True
    egress_hosts = payload.get("egress_hosts")
    if egress_hosts is None and preset:
        egress_hosts = preset.get("egress_hosts") or []
    elif isinstance(egress_hosts, list) and not egress_hosts and preset:
        egress_hosts = preset.get("egress_hosts") or []
    metadata = payload.get("metadata")
    if metadata is None and preset:
        metadata = preset.get("metadata") or {}
    elif isinstance(metadata, dict) and not metadata and preset:
        metadata = preset.get("metadata") or {}
    enabled = bool(payload.get("enabled", True))

    connector = {
        "connector_id": connector_id,
        "tenant_id": tenant_id,
        "owner_email": actor,
        "display_name": display_name,
        "transport": transport,
        "endpoint_url": endpoint_url,
        "launch_command": launch_command,
        "launch_args": list(launch_args or []),
        "launch_env": dict(launch_env or {}),
        "auth_kind": auth_kind,
        "auth_secret_key": _auth_secret_key(connector_id) if auth_kind == "bearer" else "",
        "tool_allowlist": list(tool_allowlist or []),
        "tool_denylist": list(tool_denylist or []),
        "read_only": bool(read_only),
        "egress_hosts": list(egress_hosts or []),
        "preset_id": preset_id,
        "enabled": enabled,
        "active": True,
        "metadata": dict(metadata or {}),
    }
    validate_connector_egress(connector)

    existing = conn.execute(
        "SELECT connector_id FROM main.admin_mcp_connectors WHERE connector_id = ? LIMIT 1",
        [connector_id],
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE main.admin_mcp_connectors
            SET tenant_id = ?, owner_email = ?, display_name = ?, transport = ?, endpoint_url = ?,
                launch_command = ?, launch_args_json = ?, launch_env_json = ?,
                auth_kind = ?, auth_secret_key = ?, tool_allowlist_json = ?,
                tool_denylist_json = ?, read_only = ?, egress_hosts_json = ?,
                preset_id = ?, enabled = ?, active = true, metadata_json = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE connector_id = ?
            """,
            [
                tenant_id,
                actor,
                display_name,
                transport,
                endpoint_url or None,
                launch_command or None,
                _stable_json(connector["launch_args"]),
                json.dumps(connector["launch_env"], ensure_ascii=False, sort_keys=True),
                auth_kind,
                connector["auth_secret_key"] or None,
                _stable_json(connector["tool_allowlist"]),
                _stable_json(connector["tool_denylist"]),
                bool(read_only),
                _stable_json(connector["egress_hosts"]),
                preset_id or None,
                enabled,
                json.dumps(connector["metadata"], ensure_ascii=False, sort_keys=True),
                connector_id,
            ],
        )
        return

    conn.execute(
        """
        INSERT INTO main.admin_mcp_connectors (
            connector_id, tenant_id, owner_email, display_name, transport, endpoint_url,
            launch_command, launch_args_json, launch_env_json, auth_kind, auth_secret_key,
            tool_allowlist_json, tool_denylist_json, read_only, egress_hosts_json,
            preset_id, enabled, active, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, true, ?)
        """,
        [
            connector_id,
            tenant_id,
            actor,
            display_name,
            transport,
            endpoint_url or None,
            launch_command or None,
            _stable_json(connector["launch_args"]),
            json.dumps(connector["launch_env"], ensure_ascii=False, sort_keys=True),
            auth_kind,
            connector["auth_secret_key"] or None,
            _stable_json(connector["tool_allowlist"]),
            _stable_json(connector["tool_denylist"]),
            bool(read_only),
            _stable_json(connector["egress_hosts"]),
            preset_id or None,
            enabled,
            json.dumps(connector["metadata"], ensure_ascii=False, sort_keys=True),
        ],
    )


def _apply_set_mcp_connector_auth(conn: Any, payload: dict) -> None:
    from duckclaw.write_handlers.runtime import _apply_upsert_runtime_setting

    connector_id = str(payload.get("connector_id") or "").strip()
    tenant_id = str(payload.get("tenant_id") or "default")
    actor = str(payload.get("actor_email") or "system").strip().lower()
    bearer = str(payload.get("bearer_token") or "").strip()
    if not connector_id:
        raise ValueError("connector_id required")
    if not bearer:
        raise ValueError("bearer_token required")

    row = conn.execute(
        "SELECT auth_secret_key FROM main.admin_mcp_connectors "
        "WHERE connector_id = ? AND tenant_id = ? AND active = true LIMIT 1",
        [connector_id, tenant_id],
    ).fetchone()
    if not row:
        raise ValueError(f"connector not found: {connector_id}")
    secret_key = str(row[0] if not isinstance(row, dict) else row.get("auth_secret_key") or "")
    if not secret_key:
        secret_key = _auth_secret_key(connector_id)
        conn.execute(
            "UPDATE main.admin_mcp_connectors SET auth_secret_key = ?, auth_kind = 'bearer', updated_at = CURRENT_TIMESTAMP "
            "WHERE connector_id = ? AND tenant_id = ?",
            [secret_key, connector_id, tenant_id],
        )

    _apply_upsert_runtime_setting(
        conn,
        {
            "tenant_id": tenant_id,
            "actor_email": actor,
            "domain": "mcp_connector",
            "key": secret_key,
            "value": bearer,
            "secret": True,
            "updated_by": actor,
        },
    )
    refresh = str(payload.get("refresh_token") or "").strip()
    if refresh:
        _apply_upsert_runtime_setting(
            conn,
            {
                "tenant_id": tenant_id,
                "actor_email": actor,
                "domain": "mcp_connector",
                "key": f"{connector_id}.refresh",
                "value": refresh,
                "secret": True,
                "updated_by": actor,
            },
        )


def _apply_grant_worker_mcp_connector(conn: Any, payload: dict) -> None:
    connector_id = str(payload.get("connector_id") or "").strip()
    worker_uid = str(payload.get("worker_uid") or "").strip()
    permission = str(payload.get("permission") or "use").strip() or "use"
    actor = str(payload.get("actor_email") or "system").strip().lower() or "system"
    if not connector_id or not worker_uid:
        raise ValueError("connector_id and worker_uid required")

    existing = conn.execute(
        "SELECT worker_uid FROM main.admin_worker_mcp_grants WHERE worker_uid = ? AND connector_id = ?",
        [worker_uid, connector_id],
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE main.admin_worker_mcp_grants
            SET permission = ?, active = true, updated_at = CURRENT_TIMESTAMP
            WHERE worker_uid = ? AND connector_id = ?
            """,
            [permission, worker_uid, connector_id],
        )
    else:
        conn.execute(
            """
            INSERT INTO main.admin_worker_mcp_grants (worker_uid, connector_id, permission, active)
            VALUES (?, ?, ?, true)
            """,
            [worker_uid, connector_id, permission],
        )

    preset_row = conn.execute(
        "SELECT preset_id FROM main.admin_mcp_connectors "
        "WHERE connector_id = ? AND active = true LIMIT 1",
        [connector_id],
    ).fetchone()
    preset_id = str(
        preset_row[0]
        if preset_row and not isinstance(preset_row, dict)
        else (preset_row or {}).get("preset_id") or ""
    ).strip()
    if preset_id:
        from duckclaw.mcp_connector_defaults import enable_worker_manifest_skill_for_mcp_preset

        enable_worker_manifest_skill_for_mcp_preset(
            conn,
            worker_uid=worker_uid,
            preset_id=preset_id,
            actor_email=actor,
        )


def _apply_revoke_worker_mcp_connector(conn: Any, payload: dict) -> None:
    connector_id = str(payload.get("connector_id") or "").strip()
    worker_uid = str(payload.get("worker_uid") or "").strip()
    if not connector_id or not worker_uid:
        raise ValueError("connector_id and worker_uid required")
    conn.execute(
        """
        UPDATE main.admin_worker_mcp_grants
        SET active = false, updated_at = CURRENT_TIMESTAMP
        WHERE worker_uid = ? AND connector_id = ?
        """,
        [worker_uid, connector_id],
    )


def _apply_deactivate_mcp_connector(conn: Any, payload: dict) -> None:
    connector_id = str(payload.get("connector_id") or "").strip()
    tenant_id = str(payload.get("tenant_id") or "default")
    if not connector_id:
        raise ValueError("connector_id required")
    conn.execute(
        """
        UPDATE main.admin_mcp_connectors
        SET active = false, enabled = false, updated_at = CURRENT_TIMESTAMP
        WHERE connector_id = ? AND tenant_id = ?
        """,
        [connector_id, tenant_id],
    )
    conn.execute(
        """
        UPDATE main.admin_worker_mcp_grants
        SET active = false, updated_at = CURRENT_TIMESTAMP
        WHERE connector_id = ?
        """,
        [connector_id],
    )


from duckclaw.write_handlers.registry import register_handler

register_handler("upsert_mcp_connector", _apply_upsert_mcp_connector)
register_handler("set_mcp_connector_auth", _apply_set_mcp_connector_auth)
register_handler("grant_worker_mcp_connector", _apply_grant_worker_mcp_connector)
register_handler("revoke_worker_mcp_connector", _apply_revoke_worker_mcp_connector)
register_handler("deactivate_mcp_connector", _apply_deactivate_mcp_connector)
