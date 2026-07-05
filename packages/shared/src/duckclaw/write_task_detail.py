"""Human-readable write-task status detail for admin UI polling."""

from __future__ import annotations

import json
from typing import Any


def format_write_task_success_detail(command_type: str, payload: dict[str, Any]) -> str | None:
    """Build a short success detail string from post-handler payload mutations."""
    ctype = (command_type or "").strip()
    if ctype == "sync_catalog_prompts":
        result = payload.get("_sync_result")
        if isinstance(result, dict):
            synced = _list_len(result.get("synced"))
            skipped = _list_len(result.get("skipped"))
            failed = _list_len(result.get("failed"))
            return f"synced={synced}, skipped={skipped}, failed={failed}"
    if ctype == "restore_framework_policy_pack":
        applied = payload.get("_applied")
        if isinstance(applied, list):
            return f"applied={len(applied)}"
    return None


def format_write_task_success_detail_from_ledger(command_type: str, command_json: str) -> str | None:
    """Parse ledger command_json for detail when Redis status lacks it."""
    try:
        payload = json.loads(command_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return format_write_task_success_detail(command_type, payload)


def _list_len(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    return 0
