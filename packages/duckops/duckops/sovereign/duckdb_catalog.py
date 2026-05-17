"""Inventario y selección de archivos DuckDB bajo ``db/`` del monorepo."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from duckops.sovereign.duckdb_health import human_bytes, resolve_duckdb_path
from duckops.sovereign.draft import SovereignDraft
from duckops.sovereign.wizard_reset import NEUTRAL_DUCKDB_VAULT

AXIS_VAULT_BASENAME = "axis.duckdb"
DEFAULT_AXIS_REL = "db/private/admin_duckclaw_local/axis.duckdb"


@dataclass(frozen=True)
class DuckDbPick:
    rel_path: str
    exists: bool
    size_bytes: int
    suggested: bool = False

    @property
    def size_human(self) -> str:
        return human_bytes(self.size_bytes) if self.exists else "—"


def _parse_env_file(repo_root: Path) -> dict[str, str]:
    envp = repo_root / ".env"
    if not envp.is_file():
        return {}
    out: dict[str, str] = {}
    for line in envp.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        if k.strip():
            out[k.strip()] = v.strip().strip("'\"")
    return out


def _rel_from_repo(repo_root: Path, raw: str) -> str:
    v = (raw or "").strip()
    if not v:
        return ""
    p = Path(v)
    if p.is_absolute():
        try:
            return str(p.resolve().relative_to(repo_root.resolve()))
        except ValueError:
            return v
    return v


def discover_duckdb_files(repo_root: Path) -> list[DuckDbPick]:
    """Lista recursiva ``db/**/*.duckdb``."""
    db_dir = repo_root / "db"
    if not db_dir.is_dir():
        return []
    picks: list[DuckDbPick] = []
    for path in sorted(db_dir.rglob("*.duckdb")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(repo_root))
        picks.append(
            DuckDbPick(
                rel_path=rel,
                exists=True,
                size_bytes=path.stat().st_size,
            )
        )
    return picks


def find_axis_duckdb_in_repo(repo_root: Path) -> str | None:
    """Primera ruta ``**/axis.duckdb`` bajo ``db/``."""
    db_dir = repo_root / "db"
    if not db_dir.is_dir():
        return None
    hits = sorted(db_dir.rglob(AXIS_VAULT_BASENAME))
    if not hits:
        return None
    return str(hits[0].relative_to(repo_root))


def suggest_duckdb_vault_path(
    repo_root: Path,
    draft: SovereignDraft | None = None,
) -> str:
    """
    Prioridad: borrador válido → ``DUCKCLAW_AXIS_DB_PATH`` → ``axis.duckdb`` en disco
    → ruta por defecto bajo ``db/private/``.
    """
    if draft is not None:
        cur = (draft.duckdb_vault_path or "").strip()
        if cur and resolve_duckdb_path(repo_root, cur).is_file():
            if "siata" not in cur.lower():
                return cur
    env = _parse_env_file(repo_root)
    axis_env = _rel_from_repo(repo_root, env.get("DUCKCLAW_AXIS_DB_PATH") or "")
    if axis_env:
        return axis_env
    found = find_axis_duckdb_in_repo(repo_root)
    if found:
        return found
    owner = ""
    if draft is not None:
        owner = (draft.wizard_creator_telegram_user_id or "").strip()
    if owner.isdigit():
        candidate = f"db/private/{owner}/{AXIS_VAULT_BASENAME}"
        if resolve_duckdb_path(repo_root, candidate).is_file():
            return candidate
    return DEFAULT_AXIS_REL


def format_db_folder_summary(repo_root: Path, picks: list[DuckDbPick]) -> str:
    db_dir = repo_root / "db"
    lines = [
        f"[bold]Carpeta[/] [cyan]{db_dir}[/]",
        f"  [dim]{len(picks)} archivo(s) .duckdb encontrado(s)[/]",
    ]
    if not picks:
        lines.append("  [yellow]Ninguno aún — se puede crear al aplicar.[/]")
    return "\n".join(lines)


def build_neutral_duckdb_picker(
    repo_root: Path,
) -> tuple[list[str], list[str], int]:
    """
    Opciones sin sesiones previas ni .env: solo archivos en ``db/`` + crear bóveda neutra.
    Devuelve (labels, values, initial_index).
    """
    picks = discover_duckdb_files(repo_root)
    labels: list[str] = []
    values: list[str] = []
    for p in picks:
        ex = p.size_human if p.exists else "nuevo"
        labels.append(f"{p.rel_path}  ({ex})")
        values.append(p.rel_path)
    labels.append(f"Crear nueva bóveda: {NEUTRAL_DUCKDB_VAULT}")
    values.append(NEUTRAL_DUCKDB_VAULT)
    initial = 0
    for i, v in enumerate(values):
        if v == NEUTRAL_DUCKDB_VAULT and not picks:
            initial = i
            break
    return labels, values, initial


def format_duckdb_picker_block(
    picks: list[DuckDbPick],
    *,
    highlight_rel: str | None = None,
    max_lines: int = 12,
) -> str:
    if not picks:
        return (
            "[yellow]No hay .duckdb en db/[/]\n"
            f"[dim]Enter usa la ruta sugerida ({DEFAULT_AXIS_REL}).[/]"
        )
    hid = (highlight_rel or "").strip()
    lines: list[str] = []
    for i, p in enumerate(picks[:max_lines], start=1):
        mark = ""
        if p.suggested or p.rel_path == hid:
            mark = " [bold cyan]← sugerido[/]"
        elif p.rel_path.endswith(AXIS_VAULT_BASENAME):
            mark = " [dim](axis)[/]"
        ex = f"[green]{p.size_human}[/]" if p.exists else "[dim]nuevo[/]"
        lines.append(f"  [dim]{i:2}.[/] [bold]{p.rel_path}[/] · {ex}{mark}")
    extra = len(picks) - max_lines
    if extra > 0:
        lines.append(f"  [dim]… y {extra} más[/]")
    lines.append("[dim]Número, ruta relativa o Enter = sugerido[/]")
    return "\n".join(lines)


def resolve_duckdb_choice(user_input: str, picks: list[DuckDbPick], fallback: str) -> str:
    raw = (user_input or "").strip()
    if not raw:
        return fallback
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(picks):
            return picks[idx - 1].rel_path
    p = Path(raw)
    if p.is_absolute():
        return raw
    if raw.endswith(".duckdb"):
        return raw if not raw.startswith("db/") else raw
    return raw


def picks_with_suggestion(
    repo_root: Path,
    suggested_rel: str,
) -> list[DuckDbPick]:
    """Catálogo con marca de sugerido; añade la ruta sugerida si no está en disco."""
    picks = discover_duckdb_files(repo_root)
    rels = {p.rel_path for p in picks}
    sug = (suggested_rel or "").strip()
    out: list[DuckDbPick] = []
    for p in picks:
        out.append(
            DuckDbPick(
                rel_path=p.rel_path,
                exists=p.exists,
                size_bytes=p.size_bytes,
                suggested=p.rel_path == sug,
            )
        )
    if sug and sug not in rels:
        abs_p = resolve_duckdb_path(repo_root, sug)
        out.insert(
            0,
            DuckDbPick(
                rel_path=sug,
                exists=abs_p.is_file(),
                size_bytes=abs_p.stat().st_size if abs_p.is_file() else 0,
                suggested=True,
            ),
        )
    elif out and not any(p.suggested for p in out):
        for i, p in enumerate(out):
            if p.rel_path == sug:
                out[i] = DuckDbPick(
                    rel_path=p.rel_path,
                    exists=p.exists,
                    size_bytes=p.size_bytes,
                    suggested=True,
                )
                break
    return out


def ensure_duckdb_vault(repo_root: Path, rel_path: str) -> bool:
    from duckops.sovereign.materialize import ensure_duckdb_file  # noqa: PLC0415

    return ensure_duckdb_file(repo_root, rel_path)
