"""Seed the DB worker catalog from filesystem templates.

Idempotent: skips already-imported versions. Designed to run on
``duckops init`` or gateway bootstrap.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


def seed_catalog_from_templates(
    db: Any,
    *,
    owner_email: str,
    templates_root: str | Path,
    include_template_ids: tuple[str, ...] = ("default",),
    tenant_id: str = "default",
) -> dict[str, int]:
    """Import filesystem templates into DB catalog if not already present.

    By default only imports ``default``. Pass ``include_template_ids=()`` to
    import all templates, or explicit IDs to import specific ones.

    After import, forces ``tenant_id`` on all imported rows so that
    ``list_catalog_template_ids(db, tenant_id=tenant_id)`` finds them.

    Idempotent: re-runs are safe (skips identical versions).
    """
    from duckclaw.admin_worker_catalog import ensure_admin_worker_catalog_schema
    from duckclaw.admin_template_import import import_templates_to_catalog

    ensure_admin_worker_catalog_schema(db)

    summary: dict[str, int] = {"imported": 0, "skipped": 0, "failed": 0}

    try:
        result = import_templates_to_catalog(
            db,
            owner_email=owner_email,
            templates_root=str(templates_root),
            include_template_ids=include_template_ids,
            exclude_template_ids=(),
        )
        summary["imported"] = len(result.get("imported", []))
        summary["skipped"] = len(result.get("skipped_existing", []))
        if summary["imported"]:
            safe_tid = tenant_id.replace("'", "''")
            db.execute(
                f"UPDATE main.admin_worker_catalog SET tenant_id = '{safe_tid}' "
                f"WHERE tenant_id != '{safe_tid}'"
            )
            try:
                db.execute(
                    f"UPDATE main.admin_user_profiles SET tenant_id = '{safe_tid}' "
                    f"WHERE tenant_id != '{safe_tid}'"
                )
            except Exception:
                pass
        _log.info(
            "catalog seed: %d imported, %d skipped (tenant_id=%s)",
            summary["imported"],
            summary["skipped"],
            tenant_id,
        )
    except Exception as exc:
        _log.error("catalog seed failed: %s", exc)
        summary["failed"] = 1

    return summary


def seed_catalog_if_empty(
    db: Any,
    *,
    owner_email: str = "system@duckclaw.local",
    templates_root: str | Path | None = None,
    tenant_id: str = "default",
) -> bool:
    """Seed catalog only if it's empty. Returns True if seeding happened."""
    from duckclaw.catalog_worker import list_catalog_template_ids

    existing = list_catalog_template_ids(db, tenant_id=tenant_id)
    if existing:
        _log.debug("catalog already seeded (%d workers), skipping", len(existing))
        return False

    if templates_root is None:
        from duckclaw.forge import WORKERS_TEMPLATES_DIR

        templates_root = str(WORKERS_TEMPLATES_DIR)

    result = seed_catalog_from_templates(
        db,
        owner_email=owner_email,
        templates_root=templates_root,
        tenant_id=tenant_id,
    )
    return result["imported"] > 0
