"""Optional worker templates bundled with DuckClaw (forge/seed): list them and import one.

Before this there was no way to add them from the admin (only a CLI). The import goes through the
DB-Writer like any other admin mutation: the response carries a task_id the client polls.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from routers.admin_domains.template_contexts import _problem, actor_from_header, require_admin_key

router = APIRouter(tags=["admin-seed-templates"])


def _seed_root() -> Path:
    from duckclaw.forge import WORKERS_TEMPLATES_DIR

    return Path(WORKERS_TEMPLATES_DIR)


def bundled_seed_templates() -> list[dict[str, Any]]:
    """Seed templates a user can import (the internal scaffold excluded)."""
    import yaml

    from duckclaw.admin_worker_catalog import sanitize_catalog_worker_id

    out: list[dict[str, Any]] = []
    for template_dir in sorted(p for p in _seed_root().iterdir() if p.is_dir()):
        manifest_path = template_dir / "manifest.yaml"
        if not manifest_path.is_file():
            continue
        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        if data.get("internal_scaffold"):
            continue
        out.append(
            {
                "template_id": template_dir.name,
                "worker_id": sanitize_catalog_worker_id(str(data.get("id") or template_dir.name)),
                "name": str(data.get("display_name") or data.get("name") or template_dir.name),
                "description": " ".join(str(data.get("description") or "").split()),
            }
        )
    return out


@router.get("/templates/seed", dependencies=[Depends(require_admin_key)])
async def list_seed_templates(actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_worker_catalog import get_visible_worker_for_actor

    def _load() -> list[dict[str, Any]]:
        templates = bundled_seed_templates()
        with open_gateway_db(read_only=True) as db:
            for item in templates:
                item["imported"] = bool(
                    get_visible_worker_for_actor(db, actor_email=actor, worker_id=item["worker_id"])
                )
        return templates

    return {"templates": await asyncio.to_thread(_load)}


@router.post("/templates/seed/{template_id}/import", dependencies=[Depends(require_admin_key)])
async def import_seed_template(template_id: str, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    from duckclaw.gateway_enqueue import enqueue_admin_command
    from duckclaw.write_commands import ImportTemplatesToCatalogCommand

    # Only bundled templates: the client never chooses a filesystem path.
    if template_id not in {t["template_id"] for t in bundled_seed_templates()}:
        raise _problem(404, "Plantilla no encontrada", template_id)
    command = ImportTemplatesToCatalogCommand(
        actor_email=actor,
        templates_root=str(_seed_root()),
        include_template_ids=[template_id],
    )
    task_id = enqueue_admin_command(command)
    return {"ok": True, "accepted": True, "task_id": task_id}
