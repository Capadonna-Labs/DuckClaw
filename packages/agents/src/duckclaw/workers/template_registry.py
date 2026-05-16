"""Resolución de ids de plantillas forge/templates (carpeta, agent_id, alias)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


def _templates_dir(templates_root: Path | None = None) -> Path:
    if templates_root is not None:
        return Path(templates_root)
    from duckclaw.forge import WORKERS_TEMPLATES_DIR

    return WORKERS_TEMPLATES_DIR


def list_template_ids(templates_root: Path | None = None) -> list[str]:
    """Ids canónicos = nombre de carpeta con manifest.yaml."""
    root = _templates_dir(templates_root)
    if not root.is_dir():
        return []
    return sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir() and (d / "manifest.yaml").is_file()
    )


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
        deps = data.get("dependencies")
        if isinstance(deps, dict):
            agents = deps.get("agents")
            if isinstance(agents, list):
                for a in agents:
                    if isinstance(a, str) and a.strip():
                        # agent_id corto en dependencies → carpeta AXIS-* si existe
                        short = a.strip().lower()
                        axis = f"axis-{short.replace('_', '-')}"
                        if axis in index:
                            index[short] = index[axis]
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
    2) Alias global del registry (p. ej. maestro → AXIS-Maestro).
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
