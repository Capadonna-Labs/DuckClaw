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
    """Roots permitted for folder ingest (read). Includes repo root when configured.

    Si ``DUCKCLAW_VAULT_MIRROR_DIR`` está definido, se antepone (preferencia offline local).
    """
    roots = _parse_env_roots("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS", include_repo_root=True)
    try:
        from duckclaw.vault_mirror import vault_mirror_dir

        mirror = vault_mirror_dir()
    except Exception:
        mirror = None
    if mirror is not None:
        mirror_resolved = mirror.expanduser().resolve()
        roots = [r for r in roots if r != mirror_resolved]
        roots.insert(0, mirror_resolved)
    return roots


def knowledge_output_roots() -> list[Path]:
    """Roots permitted for agent markdown output. Falls back to ingest roots.

    Antepone ``{VAULT_MIRROR}/output`` cuando hay espejo local.
    """
    output = _parse_env_roots("DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS", include_repo_root=False)
    try:
        from duckclaw.vault_mirror import vault_mirror_dir

        mirror = vault_mirror_dir()
    except Exception:
        mirror = None
    if mirror is not None:
        mirror_out = (mirror / "output").expanduser().resolve()
        output = [r for r in output if r != mirror_out]
        output.insert(0, mirror_out)
    if output:
        return output
    return knowledge_allowed_roots()


def relative_path_under_output_root(path: Path, roots: list[Path] | None = None) -> tuple[Path, str] | None:
    """Si ``path`` cae bajo alguna OUTPUT root, devuelve (root, relative_posix)."""
    resolved = path.expanduser().resolve()
    candidates = roots if roots is not None else knowledge_output_roots()
    best: tuple[Path, str] | None = None
    best_len = -1
    for root in candidates:
        root_r = root.expanduser().resolve()
        try:
            rel = resolved.relative_to(root_r)
        except ValueError:
            continue
        if len(str(root_r)) > best_len:
            best = (root_r, rel.as_posix())
            best_len = len(str(root_r))
    return best


def replicate_file_to_all_output_roots(
    primary: Path,
    *,
    roots: list[Path] | None = None,
) -> list[str]:
    """Copia ``primary`` a todas las OUTPUT roots con la misma ruta relativa.

    Garantiza trazabilidad local (espejo) + nube (Drive) cuando hay varias roots.
    Devuelve la lista de paths absolutos que quedaron escritos (incluye primary).
    """
    import shutil

    primary_r = primary.expanduser().resolve()
    if not primary_r.is_file():
        raise ValueError(f"archivo primario no existe: {primary}")
    out_roots = roots if roots is not None else knowledge_output_roots()
    if not out_roots:
        return [str(primary_r)]

    matched = relative_path_under_output_root(primary_r, out_roots)
    if matched is None:
        # Primary fuera de roots: solo devolver el path original.
        return [str(primary_r)]

    _root, rel = matched
    written: list[str] = []
    seen: set[str] = set()
    for root in out_roots:
        dest = (root.expanduser().resolve() / rel).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest != primary_r:
            shutil.copy2(primary_r, dest)
        key = str(dest)
        if key not in seen:
            seen.add(key)
            written.append(key)
    if str(primary_r) not in seen:
        written.insert(0, str(primary_r))
    return written


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


def browse_knowledge_directories(
    path: str = "",
    *,
    include_suffixes: list[str] | None = None,
    root_set: str = "allowed",
) -> dict[str, Any]:
    """List selectable folders (and optional files) under ingest or OUTPUT roots."""
    mode = (root_set or "allowed").strip().lower()
    if mode == "output":
        allowed = knowledge_output_roots()
        empty_msg = "DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS no configurado"
    else:
        allowed = knowledge_allowed_roots()
        empty_msg = "DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS no configurado para ingesta local"
    if not allowed:
        raise ValueError(empty_msg)

    suffixes: list[str] = []
    for raw in include_suffixes or []:
        item = str(raw).strip()
        if not item:
            continue
        # "*" = todos los archivos; no convertir a ".*" (sufijo literal inválido).
        if item == "*":
            suffixes.append("*")
        elif item.startswith("."):
            suffixes.append(item.lower())
        else:
            suffixes.append(f".{item.lower()}")

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
            "include_suffixes": suffixes,
            "root_set": mode,
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

    dir_entries: list[dict[str, Any]] = []
    file_entries: list[dict[str, Any]] = []
    try:
        children = sorted(target.iterdir(), key=lambda item: item.name.lower())
    except PermissionError as exc:
        raise ValueError(f"Sin permiso para listar la carpeta: {target}") from exc

    for child in children:
        if child.name.startswith("."):
            continue
        resolved_child = child.resolve()
        if child.is_dir():
            dir_entries.append(
                {
                    "name": child.name,
                    "path": str(resolved_child),
                    "kind": "directory",
                    "exists": True,
                    "selectable": True,
                }
            )
            continue
        if not suffixes or not child.is_file():
            continue
        if suffixes != ["*"] and child.suffix.lower() not in suffixes:
            continue
        file_entries.append(
            {
                "name": child.name,
                "path": str(resolved_child),
                "kind": "file",
                "exists": True,
                "selectable": True,
            }
        )

    return {
        "path": str(target),
        "parent_path": parent_path,
        "roots_mode": False,
        "entries": dir_entries + file_entries,
        "include_suffixes": suffixes,
        "root_set": mode,
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
    cleaned = (relative_path or "").replace("\\", "/").strip().strip("'\"")
    if not cleaned:
        raise ValueError("relative_path vacío")

    ingest_roots = knowledge_allowed_roots()
    output_roots = knowledge_output_roots()
    roots = list(dict.fromkeys(ingest_roots + output_roots))
    if not roots:
        raise ValueError("No hay raíces de conocimiento configuradas")

    absolute = Path(cleaned).expanduser()
    if absolute.is_absolute():
        resolved = absolute.resolve()
        if resolved.is_file() and path_under_any_root(resolved, roots):
            return resolved
        raise ValueError(f"Ruta absoluta fuera de raíces permitidas o inexistente: {cleaned}")

    cleaned = cleaned.lstrip("/")
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


def project_convert_output_relative(*, source: Path, output_format: str) -> str:
    """Map a readable source file to a relative path under OUTPUT_ROOTS for convert."""
    fmt = (output_format or "docx").strip().lower().lstrip(".")
    if not fmt:
        raise ValueError("output_format vacío")
    resolved = source.expanduser().resolve()
    out_roots = knowledge_output_roots()
    allowed = knowledge_allowed_roots()

    for root in list(dict.fromkeys(out_roots + allowed)):
        try:
            rel = resolved.relative_to(root.expanduser().resolve())
        except ValueError:
            continue
        return str(Path(rel).with_suffix(f".{fmt}")).replace("\\", "/")

    return f"{resolved.stem}.{fmt}"
