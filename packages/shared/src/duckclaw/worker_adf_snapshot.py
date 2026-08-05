"""Load worker ADF (manifest + files) from DB catalog or default seed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from duckclaw.admin_worker_catalog import get_latest_worker_version, get_worker_by_tenant_worker_id

_IMPORT_FILE_SUFFIXES = {".yaml", ".yml", ".md", ".sql", ".txt", ".json", ".py"}


def _read_seed_default(worker_id: str) -> tuple[dict[str, Any], dict[str, str], dict[str, Any] | None]:
    if worker_id != "default":
        raise FileNotFoundError(f"Worker '{worker_id}' not in catalog and not default seed")
    seed_dir = Path(__file__).resolve().parents[3] / "agents" / "src" / "duckclaw" / "forge" / "seed" / "default"
    if not seed_dir.is_dir():
        raise FileNotFoundError(f"Default seed not found: {seed_dir}")
    manifest_path = seed_dir / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    if not isinstance(manifest, dict):
        manifest = {}
    files: dict[str, str] = {}
    for path in sorted(seed_dir.rglob("*"), key=lambda p: str(p.relative_to(seed_dir))):
        if not path.is_file() or path.suffix.lower() not in _IMPORT_FILE_SUFFIXES:
            continue
        rel = str(path.relative_to(seed_dir))
        files[rel] = path.read_text(encoding="utf-8")
    return manifest, files, None


def load_worker_adf_snapshot(
    db: Any,
    worker_id: str,
    *,
    tenant_id: str = "default",
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any] | None]:
    """Return (manifest, files, catalog_row). catalog_row is None for filesystem default."""
    cat = get_worker_by_tenant_worker_id(db, tenant_id=tenant_id, worker_id=worker_id)
    if not cat:
        return _read_seed_default(worker_id)

    ver = get_latest_worker_version(db, worker_uid=cat["worker_uid"])
    if not ver:
        raise FileNotFoundError(f"Worker '{worker_id}' has no versions in catalog")

    manifest_raw = ver.get("manifest_snapshot_json") or "{}"
    files_raw = ver.get("files_snapshot_json") or "{}"
    manifest = json.loads(manifest_raw) if isinstance(manifest_raw, str) else dict(manifest_raw or {})
    files = json.loads(files_raw) if isinstance(files_raw, str) else dict(files_raw or {})
    if not isinstance(manifest, dict):
        manifest = {}
    if not isinstance(files, dict):
        files = {}
    return manifest, files, cat
