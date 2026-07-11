"""Resolución de ids de plantillas forge/templates (carpeta, agent_id, alias)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


def _templates_dir(templates_root: Path | None = None) -> Path:
    if templates_root is not None:
        return Path(templates_root)
    from duckclaw.forge import WORKERS_TEMPLATES_DIR

    return WORKERS_TEMPLATES_DIR


def _filesystem_template_ids(root: Path) -> list[str]:
    """Filesystem bootstrap is intentionally limited to the default worker."""
    default_dir = root / "default"
    if root.is_dir() and default_dir.is_dir() and (default_dir / "manifest.yaml").is_file():
        return ["default"]
    return []


def list_template_ids(
    templates_root: Path | None = None,
    db: Any | None = None,
    tenant_id: str = "default",
) -> list[str]:
    """Ids canónicos = default filesystem template + DB catalog (if db provided)."""
    root = _templates_dir(templates_root)
    fs_ids = _filesystem_template_ids(root)

    cat_ids: list[str] = []
    if db is not None:
        try:
            from duckclaw.catalog_worker import list_catalog_template_ids

            cat_ids = list_catalog_template_ids(db, tenant_id)
        except Exception:
            pass

    seen: set[str] = set()
    merged: list[str] = []
    for wid in fs_ids + cat_ids:
        if wid not in seen:
            seen.add(wid)
            merged.append(wid)
    return merged


@lru_cache(maxsize=4)
def _alias_index_cached(templates_root_str: str) -> dict[str, str]:
    root = Path(templates_root_str)
    index: dict[str, str] = {}
    for folder in list_template_ids(root):
        index[folder.strip().lower()] = folder
        manifest = root / folder / "manifest.yaml"
        if not manifest.is_file() or yaml is None:
            continue
        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for key in ("id", "agent_id", "worker_id", "name"):
            raw = data.get(key)
            if isinstance(raw, str) and raw.strip():
                index[raw.strip().lower()] = folder
    return index


def build_alias_index(templates_root: Path | None = None) -> dict[str, str]:
    return dict(_alias_index_cached(str(_templates_dir(templates_root).resolve())))


def resolve_template_id(
    available: list[str],
    user_input: str,
    templates_root: Path | None = None,
) -> Optional[str]:
    """
    Resuelve input del usuario al id canónico (nombre de carpeta).
    1) Coincidencia en ``available`` (case-insensitive).
    2) Alias global del registry (p. ej. maestro → team-lead).
    """
    if not (user_input or "").strip():
        return None
    key = (user_input or "").strip().lower()
    for a in available or []:
        if (a or "").strip().lower() == key:
            return (a or "").strip()
    canonical = build_alias_index(templates_root).get(key)
    if canonical and (not available or canonical in available):
        return canonical
    if canonical and available:
        # Alias válido pero no en available: devolver si existe en disco
        if canonical in list_template_ids(templates_root):
            return canonical
    return None


def resolve_template_id_global(
    user_input: str,
    templates_root: Path | None = None,
) -> Optional[str]:
    """Resuelve sin restringir a ``available`` (webhook entry_worker_id)."""
    all_ids = list_template_ids(templates_root)
    return resolve_template_id(all_ids, user_input, templates_root)
