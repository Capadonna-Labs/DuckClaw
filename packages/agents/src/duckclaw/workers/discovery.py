"""DB-first worker discovery.

Filesystem discovery is intentionally limited to the versioned ``default``
layout. Extra workers must come from the DB catalog or from external
extensions that expose catalog rows.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

_log = logging.getLogger(__name__)


def _filesystem_worker_ids(templates_root: Optional[Path] = None) -> list[str]:
    if templates_root is not None:
        workers_dir = templates_root / "templates" / "workers"
    else:
        try:
            from duckclaw.forge import WORKERS_TEMPLATES_DIR

            workers_dir = WORKERS_TEMPLATES_DIR
        except ImportError:
            root = Path(__file__).resolve().parent.parent.parent.parent
            workers_dir = root / "templates" / "workers"

    default_dir = workers_dir / "default"
    if workers_dir.is_dir() and default_dir.is_dir() and (default_dir / "manifest.yaml").is_file():
        return ["default"]
    return []


def _catalog_worker_ids(db: Any | None, tenant_id: str) -> list[str]:
    if db is None:
        return []
    try:
        from duckclaw.catalog_worker import list_catalog_template_ids

        return list_catalog_template_ids(db, tenant_id)
    except Exception as exc:
        _log.warning("list_workers catalog fallback failed: %s", exc)
        return []


def list_workers(
    templates_root: Optional[Path] = None,
    db: Any | None = None,
    tenant_id: str = "default",
) -> list[str]:
    """Return worker ids from the default filesystem layout plus DB catalog rows."""
    seen: set[str] = set()
    merged: list[str] = []
    for worker_id in _filesystem_worker_ids(templates_root) + _catalog_worker_ids(db, tenant_id):
        if worker_id not in seen:
            seen.add(worker_id)
            merged.append(worker_id)
    return merged
