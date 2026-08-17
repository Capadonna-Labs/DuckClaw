"""Seed and refresh admin managed-workspace draft policy (orchestrator wizard)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_SEED_PATH = Path(__file__).resolve().parent / "seeds" / "managed_workspace_draft_policy_v2.json"


def _load_seed() -> dict[str, Any]:
    return json.loads(_SEED_PATH.read_text(encoding="utf-8"))


def apply_managed_workspace_draft_policy(db: Any, *, force: bool = False) -> bool:
    """
    Upsert ``manager_task/admin_workspace_managed_draft`` from the repo seed.

    Idempotent by checksum; ``force=True`` always writes a new active version.
    """
    seed = _load_seed()
    metadata = dict(seed.get("metadata") or {})
    policy_body = dict(seed.get("policy") or {})
    content = json.dumps(policy_body, ensure_ascii=False, sort_keys=True)
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    policy_type = str(metadata.get("policy_type") or "manager_task")
    policy_name = str(metadata.get("policy_name") or "admin_workspace_managed_draft")

    row = db.execute(
        """
        SELECT checksum
        FROM main.prompt_policy_registry
        WHERE policy_type = ?
          AND policy_name = ?
          AND active = true
          AND status = 'active'
        ORDER BY version DESC
        LIMIT 1
        """,
        [policy_type, policy_name],
    ).fetchone()
    existing_checksum = ""
    if row:
        existing_checksum = str(row[0] if not isinstance(row, dict) else row.get("checksum") or "")

    if not force and existing_checksum == checksum:
        return False

    version_row = db.execute(
        """
        SELECT COALESCE(MAX(version), 0)
        FROM main.prompt_policy_registry
        WHERE policy_type = ? AND policy_name = ?
        """,
        [policy_type, policy_name],
    ).fetchone()
    next_version = int(version_row[0] if version_row else 0) + 1
    policy_id = f"ppol_{policy_name}_v{next_version}"

    db.execute(
        """
        UPDATE main.prompt_policy_registry
        SET active = false, status = 'inactive', updated_at = CURRENT_TIMESTAMP
        WHERE policy_type = ? AND policy_name = ? AND active = true
        """,
        [policy_type, policy_name],
    )
    db.execute(
        """
        INSERT INTO main.prompt_policy_registry
          (policy_id, policy_type, policy_name, version, status, content, checksum, metadata_json, active)
        VALUES (?, ?, ?, ?, 'active', ?, ?, ?, true)
        """,
        [
            policy_id,
            policy_type,
            policy_name,
            next_version,
            content,
            checksum,
            json.dumps(metadata, ensure_ascii=False),
        ],
    )
    return True
