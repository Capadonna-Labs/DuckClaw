"""Sync worker prompts from DB catalog snapshots into ``prompt_policy_registry``."""

from __future__ import annotations

import hashlib
from typing import Any


def build_system_prompt_content_from_files(files: dict[str, str]) -> str:
    """Merge ``soul.md`` + ``system_prompt.md`` like ``load_system_prompt``."""

    parts: list[str] = []
    for rel in ("soul.md", "system_prompt.md"):
        raw = str(files.get(rel) or "").strip()
        if raw:
            parts.append(raw)
    if parts:
        return "\n\n---\n\n".join(parts)
    return ""


def _active_policy_checksum(db: Any, policy_type: str, policy_name: str) -> str:
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
    if not row:
        return ""
    if isinstance(row, dict):
        return str(row.get("checksum") or "")
    return str(row[0] or "")


def _catalog_worker_exists(db: Any, worker_id: str) -> bool:
    row = db.execute(
        """
        SELECT 1
        FROM main.admin_worker_catalog
        WHERE worker_id = ? AND active = true
        LIMIT 1
        """,
        [worker_id],
    ).fetchone()
    return row is not None


def sync_worker_system_prompt_policy(
    db: Any,
    *,
    worker_id: str,
    files: dict[str, str],
    actor_email: str = "template_import",
    worker_uid: str | None = None,
    force: bool = False,
) -> bool:
    """
    Upsert ``system_prompt/<worker_id>`` desde el snapshot del catálogo DB.

    Solo escribe si el worker existe en ``admin_worker_catalog`` (DB-first).
    El contenido proviene de ``files`` (snapshot versionado), no de lectura
    ad-hoc del filesystem en runtime.
    """

    wid = (worker_id or "").strip()
    if not wid:
        return False
    if wid != "default" and not _catalog_worker_exists(db, wid):
        return False
    content = build_system_prompt_content_from_files(files)
    if not content:
        return False

    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if not force and _active_policy_checksum(db, "system_prompt", wid) == checksum:
        return False

    from duckclaw.write_handlers.prompt_policies import _apply_upsert_prompt_policy

    version_row = db.execute(
        """
        SELECT COALESCE(MAX(version), 0)
        FROM main.prompt_policy_registry
        WHERE policy_type = 'system_prompt' AND policy_name = ?
        """,
        [wid],
    ).fetchone()
    next_version = int(version_row[0] if version_row else 0) + 1

    db.execute(
        """
        UPDATE main.prompt_policy_registry
        SET active = false, status = 'inactive', updated_at = CURRENT_TIMESTAMP
        WHERE policy_type = 'system_prompt' AND policy_name = ? AND active = true
        """,
        [wid],
    )
    _apply_upsert_prompt_policy(
        db,
        {
            "policy_type": "system_prompt",
            "policy_name": wid,
            "version": next_version,
            "status": "active",
            "content": content,
            "metadata": {
                "seed": "catalog_template_import",
                "owner": actor_email,
                "worker_id": wid,
                "worker_uid": (worker_uid or "").strip(),
                "source": "admin_worker_catalog",
            },
        },
    )
    return True
