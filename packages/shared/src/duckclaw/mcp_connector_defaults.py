"""Bootstrap default MCP connectors and sync worker grants from manifest skills."""

from __future__ import annotations

import logging
from typing import Any

from duckclaw.mcp_connector_presets import (
    default_mcp_connector_id,
    default_mcp_connector_preset_ids,
    manifest_skill_id_for_preset,
)

_log = logging.getLogger(__name__)

# MCP alojado Higgsfield: auth OAuth en cliente nativo; DuckClaw guarda sesión en Admin
# (admin_runtime_settings), no via env var manual.


def _fetchall(result: Any) -> list[Any]:
    if hasattr(result, "fetchall"):
        return list(result.fetchall())
    if isinstance(result, list):
        return result
    return []


def _normalize_skill_name(raw: Any) -> str:
    return str(raw or "").strip().lower().replace("-", "_")


def manifest_skill_names(manifest: dict[str, Any] | None) -> set[str]:
    """Return normalized skill names declared in a manifest dict."""
    if not isinstance(manifest, dict):
        return set()
    skills_raw = manifest.get("skills") or []
    if isinstance(skills_raw, str):
        skills_raw = [s.strip() for s in skills_raw.split(",") if s.strip()]
    if not isinstance(skills_raw, list):
        return set()
    names: set[str] = set()
    for item in skills_raw:
        if isinstance(item, str):
            key = _normalize_skill_name(item)
            if key:
                names.add(key)
            continue
        if not isinstance(item, dict):
            continue
        raw_name = item.get("name")
        if isinstance(raw_name, str):
            key = _normalize_skill_name(raw_name)
            if key:
                names.add(key)
            continue
        if len(item) == 1:
            name, _ = next(iter(item.items()))
            key = _normalize_skill_name(name)
            if key:
                names.add(key)
    return names


def manifest_has_skill(manifest: dict[str, Any] | None, skill_id: str) -> bool:
    return _normalize_skill_name(skill_id) in manifest_skill_names(manifest)


def _connector_exists(db: Any, *, connector_id: str, tenant_id: str = "") -> bool:
    del tenant_id  # connector_id is globally unique (PRIMARY KEY)
    row = db.execute(
        "SELECT connector_id FROM main.admin_mcp_connectors WHERE connector_id = ? LIMIT 1",
        [connector_id],
    )
    if hasattr(row, "fetchone"):
        return row.fetchone() is not None
    rows = _fetchall(row)
    return bool(rows)


def ensure_default_mcp_connectors(
    db: Any,
    *,
    tenant_id: str = "default",
    actor_email: str = "system",
) -> dict[str, Any]:
    """Idempotently upsert default MCP connectors (auth via Admin OAuth/session, not env)."""
    from duckclaw.write_handlers.mcp_connectors import _apply_upsert_mcp_connector

    created: list[str] = []
    for preset_id in default_mcp_connector_preset_ids():
        connector_id = default_mcp_connector_id(preset_id)
        existed = _connector_exists(db, connector_id=connector_id, tenant_id=tenant_id)
        _apply_upsert_mcp_connector(
            db,
            {
                "tenant_id": tenant_id,
                "actor_email": actor_email,
                "preset_id": preset_id,
                "connector_id": connector_id,
                "enabled": True,
            },
        )
        if not existed:
            created.append(connector_id)
    return {"created": created}



def sync_worker_mcp_grants_from_manifest(
    db: Any,
    *,
    worker_uid: str,
    tenant_id: str = "default",
    manifest: dict[str, Any] | None,
    actor_email: str = "system",
) -> dict[str, Any]:
    """Grant or revoke default MCP connectors based on manifest skills."""
    from duckclaw.write_handlers.mcp_connectors import (
        _apply_grant_worker_mcp_connector,
        _apply_revoke_worker_mcp_connector,
    )

    granted: list[str] = []
    revoked: list[str] = []
    skills = manifest_skill_names(manifest)
    for preset_id in default_mcp_connector_preset_ids():
        connector_id = default_mcp_connector_id(preset_id)
        if not _connector_exists(db, connector_id=connector_id, tenant_id=tenant_id):
            continue
        skill_key = manifest_skill_id_for_preset(preset_id)
        if skill_key in skills:
            _apply_grant_worker_mcp_connector(
                db,
                {
                    "connector_id": connector_id,
                    "worker_uid": worker_uid,
                    "permission": "use",
                },
            )
            granted.append(connector_id)
        else:
            _apply_revoke_worker_mcp_connector(
                db,
                {
                    "connector_id": connector_id,
                    "worker_uid": worker_uid,
                },
            )
            revoked.append(connector_id)
    return {"granted": granted, "revoked": revoked}


def enable_worker_manifest_skill_for_mcp_preset(
    conn: Any,
    *,
    worker_uid: str,
    preset_id: str,
    actor_email: str = "system",
) -> dict[str, Any]:
    """When granting an MCP connector, also enable the matching manifest skill (e.g. higgsfield)."""
    from duckclaw.admin_worker_catalog import (
        add_worker_version,
        get_latest_worker_version,
        sync_worker_catalog_skills_from_manifest,
    )

    from duckclaw.mcp_connector_presets import manifest_skill_id_for_preset

    skill_id = _normalize_skill_name(manifest_skill_id_for_preset(preset_id))
    if not skill_id:
        return {"manifest_skill_enabled": False, "skill_id": ""}

    latest = get_latest_worker_version(conn, worker_uid=worker_uid) or {}
    manifest = dict(latest.get("manifest_snapshot") or {})
    files_snapshot = dict(latest.get("files_snapshot") or {})
    if manifest_has_skill(manifest, skill_id):
        sync_worker_catalog_skills_from_manifest(conn, worker_uid=worker_uid, manifest=manifest)
        return {"manifest_skill_enabled": False, "skill_id": skill_id, "already_present": True}

    skills_raw = manifest.get("skills")
    if not isinstance(skills_raw, list):
        skills_raw = []
    skills_raw = list(skills_raw)
    skills_raw.append(skill_id)
    manifest["skills"] = skills_raw

    add_worker_version(
        conn,
        worker_uid=worker_uid,
        created_by=actor_email,
        manifest_snapshot=manifest,
        files_snapshot=files_snapshot,
        change_note=f"MCP grant: habilitar skill {skill_id}",
    )
    sync_worker_catalog_skills_from_manifest(conn, worker_uid=worker_uid, manifest=manifest)
    return {"manifest_skill_enabled": True, "skill_id": skill_id}


def backfill_default_mcp_connectors_and_grants(db: Any) -> dict[str, Any]:
    """Migration hook: ensure connectors once, then sync grants per tenant/worker."""
    from duckclaw.admin_worker_catalog import get_latest_worker_version

    tenant_rows = _fetchall(
        db.execute(
            "SELECT DISTINCT tenant_id FROM main.admin_worker_catalog WHERE active = true"
        )
    )
    tenant_ids = [str(r[0] if not isinstance(r, dict) else r.get("tenant_id") or "default") for r in tenant_rows]
    if not tenant_ids:
        tenant_ids = ["default"]

    connector_summary = ensure_default_mcp_connectors(
        db, tenant_id=tenant_ids[0], actor_email="system"
    )
    grant_summary: list[dict[str, Any]] = []
    for tenant_id in tenant_ids:
        worker_rows = _fetchall(
            db.execute(
                "SELECT worker_uid FROM main.admin_worker_catalog "
                "WHERE tenant_id = ? AND active = true",
                [tenant_id],
            )
        )
        for row in worker_rows:
            worker_uid = str(row[0] if not isinstance(row, dict) else row.get("worker_uid") or "")
            if not worker_uid:
                continue
            latest = get_latest_worker_version(db, worker_uid=worker_uid) or {}
            manifest = dict(latest.get("manifest_snapshot") or {})
            result = sync_worker_mcp_grants_from_manifest(
                db,
                worker_uid=worker_uid,
                tenant_id=tenant_id,
                manifest=manifest,
                actor_email="system",
            )
            if result["granted"] or result["revoked"]:
                grant_summary.append({"worker_uid": worker_uid, **result})

    return {"connectors": connector_summary, "grants": grant_summary}
