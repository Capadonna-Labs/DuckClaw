"""Prompt policy registry typed write handlers."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _json_metadata(raw: Any) -> str:
    data = raw if isinstance(raw, dict) else {}
    return json.dumps(data, ensure_ascii=False, default=str)


_PROMPT_POLICY_ALIASES = {
    "capabilities": "capability",
    "directives": "directive",
    "manager_tasks": "manager_task",
    "system_prompts": "system_prompt",
}
_PROMPT_POLICY_TYPES = {"directive", "capability", "system_prompt", "manager_task", "tool_directive"}
_PROMPT_POLICY_STATUSES = {"draft", "active", "inactive", "archived"}


def _normalize_prompt_policy_type(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    normalized = _PROMPT_POLICY_ALIASES.get(value, value)
    if normalized not in _PROMPT_POLICY_TYPES:
        raise ValueError(f"Invalid prompt policy type: {raw}")
    return normalized


def _prompt_policy_id(policy_type: str, policy_name: str, version: int) -> str:
    digest = hashlib.sha256(f"{policy_type}:{policy_name}:{version}".encode("utf-8")).hexdigest()
    return f"ppol_{digest[:24]}"


def _apply_upsert_prompt_policy(conn: Any, payload: dict) -> None:
    policy_type = _normalize_prompt_policy_type(payload.get("policy_type"))
    policy_name = str(payload.get("policy_name") or "").strip()
    if not policy_name:
        raise ValueError("policy_name required")
    version = int(payload.get("version") or 1)
    if version < 1:
        raise ValueError("version must be >= 1")
    status = str(payload.get("status") or "active").strip().lower()
    if status not in _PROMPT_POLICY_STATUSES:
        raise ValueError(f"Invalid prompt policy status: {status}")
    content = str(payload.get("content") or "")
    if not content.strip():
        raise ValueError("content required")
    metadata_json = _json_metadata(payload.get("metadata"))
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    active = status == "active"

    existing = conn.execute(
        "SELECT policy_id FROM main.prompt_policy_registry "
        "WHERE policy_type = ? AND policy_name = ? AND version = ?",
        [policy_type, policy_name, version],
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE main.prompt_policy_registry "
            "SET status = ?, content = ?, checksum = ?, metadata_json = ?, "
            "active = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE policy_type = ? AND policy_name = ? AND version = ?",
            [status, content, checksum, metadata_json, active, policy_type, policy_name, version],
        )
    else:
        policy_id = str(payload.get("policy_id") or "").strip() or _prompt_policy_id(
            policy_type,
            policy_name,
            version,
        )
        conn.execute(
            "INSERT INTO main.prompt_policy_registry "
            "(policy_id, policy_type, policy_name, version, status, content, checksum, metadata_json, active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [policy_id, policy_type, policy_name, version, status, content, checksum, metadata_json, active],
        )


def _apply_deactivate_prompt_policy(conn: Any, payload: dict) -> None:
    policy_type = _normalize_prompt_policy_type(payload.get("policy_type"))
    policy_name = str(payload.get("policy_name") or "").strip()
    if not policy_name:
        raise ValueError("policy_name required")
    raw_version = payload.get("version")
    params: list[Any] = [policy_type, policy_name]
    version_clause = ""
    if raw_version is not None:
        version = int(raw_version)
        if version < 1:
            raise ValueError("version must be >= 1")
        version_clause = " AND version = ?"
        params.append(version)
    row = conn.execute(
        "SELECT policy_id FROM main.prompt_policy_registry "
        "WHERE policy_type = ? AND policy_name = ?" + version_clause + " LIMIT 1",
        params,
    ).fetchone()
    if not row:
        raise ValueError(f"Prompt policy not found: {policy_type}/{policy_name}")
    conn.execute(
        "UPDATE main.prompt_policy_registry "
        "SET active = false, status = 'inactive', updated_at = CURRENT_TIMESTAMP "
        "WHERE policy_type = ? AND policy_name = ?" + version_clause,
        params,
    )


from duckclaw.write_handlers.registry import register_handler

register_handler("upsert_prompt_policy", _apply_upsert_prompt_policy)
register_handler("deactivate_prompt_policy", _apply_deactivate_prompt_policy)
