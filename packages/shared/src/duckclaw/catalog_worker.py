"""Load WorkerSpec from DB catalog instead of filesystem templates.

Usage::

    from duckclaw.catalog_worker import load_manifest_from_catalog
    spec = load_manifest_from_catalog(db, "worker_id", tenant_id="default")
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from duckclaw.admin_worker_catalog import get_latest_worker_version, get_worker_by_tenant_worker_id
from duckclaw.shared_db_grants import _query_all_dicts, _sql_lit

_log = logging.getLogger(__name__)

_CACHE_ROOT = Path.home() / ".duckclaw" / ".catalog_cache"


def _cache_dir(worker_uid: str, files_digest: str) -> Path:
    return _CACHE_ROOT / f"{worker_uid}_{files_digest}"


def _compute_digest(files: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(files, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


def _extract_files(files: dict[str, str], target: Path) -> None:
    for rel_path, content in files.items():
        full = target / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")


def load_manifest_from_catalog(
    db: Any,
    worker_id: str,
    tenant_id: str = "default",
) -> Any:
    """Build a WorkerSpec from the DB catalog.

    Returns a WorkerSpec identical to what ``load_manifest()`` returns
    from filesystem, with ``worker_dir`` pointing to a content-addressed
    cache directory populated from the version snapshot.

    Raises ``FileNotFoundError`` if the worker is not found in the catalog
    or has no versions.
    """
    cat = get_worker_by_tenant_worker_id(
        db,
        tenant_id=tenant_id,
        worker_id=worker_id,
    )
    if not cat:
        raise FileNotFoundError(
            f"Worker '{worker_id}' not found in catalog for tenant '{tenant_id}'"
        )

    ver = get_latest_worker_version(db, worker_uid=cat["worker_uid"])
    if not ver:
        raise FileNotFoundError(
            f"Worker '{worker_id}' has no versions in catalog"
        )

    manifest_raw = ver.get("manifest_snapshot_json") or "{}"
    if isinstance(manifest_raw, str):
        manifest = json.loads(manifest_raw)
    elif isinstance(manifest_raw, dict):
        manifest = manifest_raw
    else:
        manifest = {}

    files_raw = ver.get("files_snapshot_json") or "{}"
    if isinstance(files_raw, str):
        files = json.loads(files_raw)
    elif isinstance(files_raw, dict):
        files = files_raw
    else:
        files = {}

    digest = _compute_digest(files)
    cache_path = _cache_dir(cat["worker_uid"], digest)

    if not cache_path.is_dir():
        try:
            cache_path.mkdir(parents=True, exist_ok=True)
            _extract_files(files, cache_path)
            _log.info("catalog cache populated: %s (%d files)", cache_path, len(files))
        except Exception as exc:
            _log.error("failed to populate catalog cache %s: %s", cache_path, exc)
            raise

    # Import lazily to avoid circular dependency at module level.
    from duckclaw.workers.manifest import build_spec_from_manifest

    try:
        spec = build_spec_from_manifest(manifest, worker_id, cache_path)
    except Exception as exc:
        _log.error(
            "failed to build WorkerSpec for '%s' from catalog: %s",
            worker_id,
            exc,
        )
        raise

    return spec


def list_catalog_template_ids(db: Any, tenant_id: str = "default") -> list[str]:
    """List worker IDs from the DB catalog (active workers only)."""
    try:
        rows = _query_all_dicts(
            db,
            "SELECT worker_id FROM main.admin_worker_catalog "
            f"WHERE tenant_id = '{_sql_lit(tenant_id, 128)}' "
            "AND active = true ORDER BY worker_id",
        )
        return [str(r["worker_id"]) for r in rows if r.get("worker_id")]
    except Exception as exc:
        _log.warning("list_catalog_template_ids failed: %s", exc)
        return []


def worker_exists_in_catalog(db: Any, worker_id: str, tenant_id: str = "default") -> bool:
    """Check if a worker exists in the DB catalog."""
    try:
        return get_worker_by_tenant_worker_id(db, tenant_id=tenant_id, worker_id=worker_id) is not None
    except Exception as exc:
        _log.warning("worker_exists_in_catalog(%s) failed: %s", worker_id, exc)
        return False
