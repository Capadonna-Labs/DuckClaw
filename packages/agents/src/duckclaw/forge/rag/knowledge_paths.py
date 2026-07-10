"""Path allowlists for knowledge ingest and agent output writes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

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


_MARKDOWN_EXTENSIONS = (".md", ".markdown", ".txt", ".html", ".htm")


def _basename_has_extension(name: str) -> bool:
    return "." in name and not name.endswith(".")


def normalize_output_relative_path(
    relative_path: str,
    *,
    default_extension: str = ".md",
    require_markdown: bool = False,
) -> str:
    """Normaliza ruta relativa; añade extensión solo si el basename no tiene ninguna."""
    rel = (relative_path or "").replace("\\", "/").strip().lstrip("/")
    if not rel:
        raise ValueError("relative_path vacío")
    basename = rel.rsplit("/", 1)[-1]
    if _basename_has_extension(basename):
        if require_markdown and not rel.lower().endswith(_MARKDOWN_EXTENSIONS):
            raise ValueError(
                "La conversión solo admite fuentes .md, .markdown, .txt o .html. "
                "Escribe el informe con write_output_document usando una de esas extensiones."
            )
        return rel
    ext = default_extension if default_extension.startswith(".") else f".{default_extension}"
    return f"{rel.rstrip('/')}{ext}"


def resolve_knowledge_ingest_uri(source_uri: str) -> str:
    """Resolve vault path; auto-complete truncated paste or default single allowed root."""
    uri = normalize_source_uri(source_uri)
    allowed = knowledge_allowed_roots()

    if not uri:
        existing = [root for root in allowed if root.exists()]
        if len(existing) == 1:
            return str(existing[0])
        raise ValueError(
            "Indica la ruta de la carpeta o usa el explorador de carpetas del servidor."
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
            "Usa el explorador de carpetas o pega la ruta absoluta completa."
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


def _is_allowed_root(target: Path, allowed: list[Path]) -> bool:
    resolved = target.expanduser().resolve()
    return any(resolved == root.expanduser().resolve() for root in allowed)


def browse_knowledge_directories(path: str = "") -> dict[str, Any]:
    """List selectable folders under configured ingest roots (admin folder picker)."""
    allowed = knowledge_allowed_roots()
    if not allowed:
        raise ValueError("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS no configurado para ingesta local")

    uri = normalize_source_uri(path)
    if not uri:
        entries: list[dict[str, Any]] = []
        for root in allowed:
            resolved = root.expanduser().resolve()
            entries.append(
                {
                    "name": resolved.name or str(resolved),
                    "path": str(resolved),
                    "kind": "root",
                    "exists": resolved.exists(),
                    "selectable": resolved.is_dir() and resolved.exists(),
                }
            )
        return {
            "path": "",
            "parent_path": None,
            "roots_mode": True,
            "entries": sorted(entries, key=lambda item: str(item["name"]).lower()),
        }

    target = Path(uri).expanduser().resolve()
    if not target.exists():
        raise ValueError(f"Ruta de conocimiento no existe: {uri}")
    if not path_under_any_root(target, allowed):
        raise ValueError("Ruta de conocimiento fuera de raíces permitidas")
    if not target.is_dir():
        raise ValueError("La ruta debe ser una carpeta")

    if _is_allowed_root(target, allowed):
        parent_path: str | None = ""
    else:
        parent = target.parent.resolve()
        parent_path = str(parent) if path_under_any_root(parent, allowed) else ""

    entries = []
    try:
        children = sorted(target.iterdir(), key=lambda item: item.name.lower())
    except PermissionError as exc:
        raise ValueError(f"Sin permiso para listar la carpeta: {target}") from exc

    for child in children:
        if child.name.startswith("."):
            continue
        if not child.is_dir():
            continue
        resolved_child = child.resolve()
        entries.append(
            {
                "name": child.name,
                "path": str(resolved_child),
                "kind": "directory",
                "exists": True,
                "selectable": True,
            }
        )

    return {
        "path": str(target),
        "parent_path": parent_path,
        "roots_mode": False,
        "entries": entries,
    }


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


def resolve_readable_document_path(*, relative_path: str, root_hint: str = "") -> Path:
    """Resolve a file under ALLOWED or OUTPUT roots for agent read/extract."""
    cleaned = (relative_path or "").replace("\\", "/").strip().lstrip("/")
    if not cleaned:
        raise ValueError("relative_path vacío")

    ingest_roots = knowledge_allowed_roots()
    output_roots = knowledge_output_roots()
    roots = list(dict.fromkeys(ingest_roots + output_roots))
    if not roots:
        raise ValueError("No hay raíces de conocimiento configuradas")

    if root_hint.strip():
        bases = [Path(root_hint).expanduser().resolve()]
        if not path_under_any_root(bases[0], roots):
            raise ValueError("root_hint fuera de raíces permitidas")
    else:
        if len(roots) == 1:
            bases = [roots[0]]
        else:
            bases = roots

    for base in bases:
        safe_relative_path(base, base / cleaned)
        candidate = (base / cleaned).resolve()
        if candidate.is_file() and path_under_any_root(candidate, roots):
            return candidate

    raise ValueError(f"No existe el archivo legible: {cleaned}")
