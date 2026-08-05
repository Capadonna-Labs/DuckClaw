"""Import spawn package into DB worker catalog with sanitization."""

from __future__ import annotations

import json
from typing import Any

from duckclaw.admin_template_import import _capability_names, _context_files, _same_version_exists
from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.admin_worker_catalog import (
    add_worker_context,
    add_worker_version,
    create_worker,
    get_worker_by_tenant_worker_id,
    grant_worker_capability,
    list_worker_contexts,
    register_capability,
    sanitize_catalog_worker_id,
)
from duckclaw.catalog_prompt_sync import sync_worker_system_prompt_policy
from duckclaw.spawn_risk_policy import sanitize_manifest_for_import


def import_spawn_package_to_catalog(
    db: Any,
    *,
    owner_email: str,
    manifest: dict[str, Any],
    files: dict[str, str],
    worker_id_override: str | None = None,
    force_read_only: bool = True,
) -> dict[str, Any]:
    profile = ensure_profile_for_user(db, email=owner_email)
    manifest = sanitize_manifest_for_import(manifest, force_read_only=force_read_only)
    worker_id = sanitize_catalog_worker_id(
        worker_id_override or str(manifest.get("id") or "imported-worker")
    )
    manifest = dict(manifest)
    manifest["id"] = worker_id
    display_name = str(manifest.get("display_name") or worker_id).strip()

    existing = get_worker_by_tenant_worker_id(
        db, tenant_id=profile["tenant_id"], worker_id=worker_id
    )
    if existing:
        worker = existing
        if _same_version_exists(
            db, worker_uid=worker["worker_uid"], manifest=manifest, files=files
        ):
            return {"worker_id": worker_id, "worker_uid": worker["worker_uid"], "skipped": True}
    else:
        worker = create_worker(
            db,
            owner_email=profile["email"],
            worker_id=worker_id,
            display_name=display_name,
            source_kind="spawn_import",
            source_template_id=str(manifest.get("id") or worker_id),
            visibility="private",
        )

    add_worker_version(
        db,
        worker_uid=worker["worker_uid"],
        created_by=profile["email"],
        manifest_snapshot=manifest,
        files_snapshot=files,
        change_note="Spawn package import (sanitized privileged tools)",
    )

    existing_context_titles = {
        ctx["title"] for ctx in list_worker_contexts(db, worker_uid=worker["worker_uid"])
    }
    for order, (title, content_md) in enumerate(_context_files(manifest, files), start=10):
        if title not in existing_context_titles:
            add_worker_context(
                db,
                worker_uid=worker["worker_uid"],
                title=title,
                content_md=content_md,
                sort_order=order,
            )

    for capability_name in _capability_names(manifest):
        capability = register_capability(
            db,
            name=capability_name,
            kind="manifest_capability",
            provider="spawn_import",
            risk_level="medium",
        )
        grant_worker_capability(
            db,
            worker_uid=worker["worker_uid"],
            capability_id=capability["capability_id"],
            permission="use",
        )

    sync_worker_system_prompt_policy(
        db,
        worker_id=worker_id,
        files=files,
        actor_email=profile["email"],
        worker_uid=str(worker.get("worker_uid") or ""),
    )

    return {
        "worker_id": worker_id,
        "worker_uid": worker["worker_uid"],
        "skipped": False,
        "manifest_sanitized": json.dumps(
            {"read_only": manifest.get("read_only"), "tool_surface": manifest.get("tool_surface")},
            ensure_ascii=False,
        ),
    }
