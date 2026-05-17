"""Catálogo de plantillas forge/templates para el wizard (alineado con /workers y consola admin)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


@dataclass(frozen=True)
class WorkerPick:
    """Entrada del picker: id canónico (carpeta) y etiqueta legible."""

    worker_id: str
    label: str


def _templates_dir(repo_root: Path | None) -> Path | None:
    if repo_root is None:
        return None
    p = repo_root / "packages" / "agents" / "src" / "duckclaw" / "forge" / "templates"
    return p if p.is_dir() else None


def _read_manifest_label(folder: Path) -> str:
    manifest = folder / "manifest.yaml"
    if not manifest.is_file() or yaml is None:
        return folder.name
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except OSError:
        return folder.name
    if not isinstance(data, dict):
        return folder.name
    for key in ("display_name", "name", "id", "agent_id"):
        raw = data.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return folder.name


def _scan_template_ids(templates_dir: Path) -> list[str]:
    return sorted(
        d.name
        for d in templates_dir.iterdir()
        if d.is_dir() and (d / "manifest.yaml").is_file()
    )


def list_worker_picks(repo_root: Path | None = None) -> list[WorkerPick]:
    """Lista plantillas con manifest; usa registry duckclaw si está en PYTHONPATH."""
    templates_dir = _templates_dir(repo_root)
    if templates_dir is None:
        return []

    ids: list[str] = []
    try:
        import sys

        if repo_root is not None:
            root_s = str(repo_root.resolve())
            if root_s not in sys.path:
                sys.path.insert(0, root_s)
        from duckclaw.workers.template_registry import list_template_ids

        ids = list_template_ids(templates_dir)
    except Exception:
        ids = _scan_template_ids(templates_dir)

    picks: list[WorkerPick] = []
    for wid in ids:
        folder = templates_dir / wid
        label = _read_manifest_label(folder) if folder.is_dir() else wid
        picks.append(WorkerPick(worker_id=wid, label=label))
    return picks


def format_worker_picker_block(
    picks: list[WorkerPick],
    *,
    max_lines: int = 14,
    highlight_id: str | None = None,
) -> str:
    """Texto Rich para mostrar opciones numeradas."""
    if not picks:
        return (
            "[yellow]No se encontraron plantillas en forge/templates.[/]\n"
            "[dim]Comprueba que el monorepo esté completo o escribe el id del worker a mano.[/]"
        )
    lines: list[str] = []
    hid = (highlight_id or "").strip().lower()
    for i, p in enumerate(picks[:max_lines], start=1):
        mark = " [bold cyan]← sugerido[/]" if p.worker_id.lower() == hid else ""
        lines.append(f"  [dim]{i:2}.[/] [bold]{p.worker_id}[/] — {p.label}{mark}")
    extra = len(picks) - max_lines
    if extra > 0:
        lines.append(f"  [dim]… y {extra} más (escribe el id exacto)[/]")
    lines.append("[dim]Número, id o alias · Enter = sugerido[/]")
    return "\n".join(lines)


def resolve_worker_choice(
    user_input: str,
    picks: list[WorkerPick],
    repo_root: Path | None = None,
) -> str | None:
    """Resuelve número, id o alias al id canónico de carpeta."""
    raw = (user_input or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(picks):
            return picks[idx - 1].worker_id
    available = [p.worker_id for p in picks]
    templates_dir = _templates_dir(repo_root)
    try:
        if repo_root is not None:
            import sys

            root_s = str(repo_root.resolve())
            if root_s not in sys.path:
                sys.path.insert(0, root_s)
        from duckclaw.workers.template_registry import (
            resolve_template_id,
            resolve_template_id_global,
        )

        hit = resolve_template_id(available, raw, templates_dir)
        if hit:
            return hit
        return resolve_template_id_global(raw, templates_dir)
    except Exception:
        key = raw.lower()
        for p in picks:
            if p.worker_id.lower() == key:
                return p.worker_id
        return None


def suggest_default_worker_id(
    picks: list[WorkerPick],
    current: str,
    *,
    prefer: tuple[str, ...] = ("AXIS-Maestro", "default", "BI-Analyst", "finanz"),
) -> str:
    """Mantiene el borrador si es válido; si no, elige el primer preferido presente."""
    cur = (current or "").strip()
    ids = {p.worker_id for p in picks}
    if cur and cur in ids:
        return cur
    for cand in prefer:
        if cand in ids:
            return cand
    return picks[0].worker_id if picks else cur or "default"
