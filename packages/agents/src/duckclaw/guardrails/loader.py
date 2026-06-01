"""Carga guardrails y prompts desde archivos Markdown (fuente única, sin strings en factory)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

GUARDRAILS_ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=256)
def load_worker_guardrail(worker_dir: Path | str, relative_path: str) -> str:
    """Lee guardrail relativo al directorio del template (workers externos)."""
    base = Path(worker_dir)
    rel = (relative_path or "").strip().lstrip("/")
    path = (base / rel).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"worker guardrail not found: {path}")
    if base.resolve() not in path.parents and path != base.resolve():
        raise FileNotFoundError(f"worker guardrail outside worker_dir: {path}")
    return path.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=256)
def load_guardrail(*parts: str) -> str:
    """Lee ``guardrails/<parts>.md`` (UTF-8). ``parts`` sin extensión."""
    path = GUARDRAILS_ROOT.joinpath(*parts).with_suffix(".md")
    if not path.is_file():
        raise FileNotFoundError(f"guardrail not found: {path.relative_to(GUARDRAILS_ROOT)}")
    return path.read_text(encoding="utf-8").strip()


def load_guardrail_optional(*parts: str, default: str = "") -> str:
    try:
        return load_guardrail(*parts)
    except FileNotFoundError:
        return default


def format_guardrail(*parts: str, **kwargs: str) -> str:
    """Carga un guardrail y aplica ``str.format`` con ``kwargs``."""
    return load_guardrail(*parts).format(**kwargs)


@lru_cache(maxsize=128)
def load_guardrail_task_list(*parts: str) -> tuple[str, ...]:
    """Lista de ítems de plan separados por líneas ``---`` en el .md."""
    body = load_guardrail(*parts)
    return tuple(block.strip() for block in body.split("\n---\n") if block.strip())


@lru_cache(maxsize=128)
def load_guardrail_kv(*parts: str) -> dict[str, str]:
    """Mapa ``clave=valor`` (una entrada por línea; ``#`` comentarios ignorados)."""
    out: dict[str, str] = {}
    for line in load_guardrail(*parts).splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        key, val = s.split("=", 1)
        out[key.strip()] = val.strip()
    return out


@lru_cache(maxsize=32)
def load_guardrail_pipe_table(*parts: str) -> tuple[tuple[str, str], ...]:
    """Filas ``col0|col1`` (fly commands /help)."""
    rows: list[tuple[str, str]] = []
    for line in load_guardrail(*parts).splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "|" not in s:
            continue
        left, right = s.split("|", 1)
        rows.append((left.strip(), right.strip()))
    return tuple(rows)
