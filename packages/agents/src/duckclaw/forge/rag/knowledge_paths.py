"""Path allowlists for knowledge ingest and agent output writes."""

from __future__ import annotations

import os
from pathlib import Path

from duckclaw.forge.rag.knowledge_core import safe_relative_path


def _parse_env_roots(env_key: str, *, include_repo_root: bool = False) -> list[Path]:
    roots: list[Path] = []
    raw = (os.environ.get(env_key) or "").strip()
    for item in raw.split(os.pathsep):
        cleaned = normalize_source_uri(item)
        if cleaned:
            roots.append(Path(cleaned).expanduser().resolve())
    if include_repo_root:
        repo = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
        if repo:
            roots.append(Path(repo).expanduser().resolve())
    return roots


def knowledge_allowed_roots() -> list[Path]:
    """Roots permitted for folder ingest (read). Includes repo root when configured."""
    return _parse_env_roots("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS", include_repo_root=True)


def knowledge_output_roots() -> list[Path]:
    """Roots permitted for agent markdown output. Falls back to ingest roots."""
    output = _parse_env_roots("DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS", include_repo_root=False)
    if output:
        return output
    return knowledge_allowed_roots()


def path_under_any_root(target: Path, roots: list[Path]) -> bool:
    resolved = target.expanduser().resolve()
    return any(resolved == root or root in resolved.parents for root in roots)


def normalize_source_uri(raw: str) -> str:
    return (raw or "").strip().strip("'\"")


def resolve_knowledge_ingest_uri(source_uri: str) -> str:
    """Resolve vault path; auto-complete truncated paste or default single allowed root."""
    uri = normalize_source_uri(source_uri)
    allowed = knowledge_allowed_roots()

    if not uri:
        existing = [root for root in allowed if root.exists()]
        if len(existing) == 1:
            return str(existing[0])
        raise ValueError(
            "Indica la ruta del vault o pulsa «Usar vault del servidor» si está configurado en .env."
        )

    target = Path(uri).expanduser()
    if target.exists():
        return str(target.resolve())

    for root in allowed:
        if not root.exists():
            continue
        root_str = str(root)
        if root_str.startswith(uri):
            return str(root.resolve())

    lower = uri.lower()
    if "@gmail" in lower or "cloudstorage/googledrive" in lower.replace(" ", ""):
        for root in allowed:
            if root.exists():
                return str(root.resolve())
        raise ValueError(
            "Ruta truncada o Google Drive aún no montado. "
            "Pulsa «Usar vault del servidor» en lugar de pegar a mano."
        )

    raise ValueError(f"Ruta de conocimiento no existe: {uri}")


def validate_knowledge_ingest_root(source_uri: str) -> Path:
    resolved = resolve_knowledge_ingest_uri(source_uri)
    target = Path(resolved)
    allowed = knowledge_allowed_roots()
    if not allowed:
        raise ValueError("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS no configurado para ingesta local")
    if not path_under_any_root(target, allowed):
        raise ValueError("Ruta de conocimiento fuera de raíces permitidas")
    return target


def resolve_knowledge_output_path(*, relative_path: str, output_root: str = "") -> Path:
    """Resolve a safe output file path under configured OUTPUT_ROOTS."""
    roots = knowledge_output_roots()
    if not roots:
        raise ValueError("DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS no configurado para escritura")

    cleaned = (relative_path or "").replace("\\", "/").strip().lstrip("/")
    if not cleaned:
        raise ValueError("relative_path vacío")

    if output_root.strip():
        base = Path(output_root).expanduser().resolve()
        if not path_under_any_root(base, roots):
            raise ValueError("output_root fuera de raíces de salida permitidas")
    else:
        if len(roots) == 1:
            base = roots[0]
        else:
            raise ValueError(
                "Hay varias raíces de salida; indica output_root explícitamente"
            )

    safe_relative_path(base, base / cleaned)
    target = (base / cleaned).resolve()
    if not path_under_any_root(target.parent if target.suffix else target, roots):
        raise ValueError("ruta de salida fuera de raíces permitidas")
    return target
