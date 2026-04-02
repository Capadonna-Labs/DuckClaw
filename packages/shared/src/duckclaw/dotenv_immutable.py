"""Política de escritura del ``.env`` en la raíz del repo.

Si el usuario crea ``.env.immutable`` (archivo vacío basta) o exporta
``DUCKCLAW_DOTENV_IMMUTABLE=1``, ni el Sovereign Wizard ni scripts de setup
modifican ``.env``. Los valores que habrían fusionado se escriben en
``config/dotenv_wizard_proposed.env`` para copia manual.

Escape hatch (tests / CI): ``DUCKCLAW_DOTENV_ALLOW_WRITE=1`` desactiva el bloqueo.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_IMMUTABLE = "DUCKCLAW_DOTENV_IMMUTABLE"
_ENV_ALLOW_WRITE = "DUCKCLAW_DOTENV_ALLOW_WRITE"
_SENTINEL = ".env.immutable"
_PROPOSED_REL = Path("config") / "dotenv_wizard_proposed.env"


def parse_dotenv_file(path: Path) -> dict[str, str]:
    """Lee ``KEY=value`` desde un archivo; devuelve ``{}`` si no existe (sin crear directorios)."""
    p = Path(path)
    if not p.is_file():
        return {}
    out: dict[str, str] = {}
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key, _, val = s.partition("=")
            ks = key.strip()
            if not ks:
                continue
            out[ks] = val.strip().strip("'\"")
    except OSError:
        return {}
    return out


def merged_root_and_proposed_flat_env(repo_root: Path | str) -> dict[str, str]:
    """
    Fusión para runtime/wizard: ``.env`` de la raíz y luego overlay de
    ``config/dotenv_wizard_proposed.env`` (gana el propuesto en colisiones).
    """
    root = Path(repo_root).resolve()
    out = parse_dotenv_file(root / ".env")
    out.update(parse_dotenv_file(root / _PROPOSED_REL))
    return out


def is_repo_dotenv_immutable(repo_root: Path | str) -> bool:
    root = Path(repo_root).resolve()
    if (os.environ.get(_ENV_ALLOW_WRITE) or "").strip().lower() in ("1", "true", "yes", "on"):
        return False
    if (os.environ.get(_ENV_IMMUTABLE) or "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return (root / _SENTINEL).is_file()


def proposed_env_path(repo_root: Path | str) -> Path:
    p = Path(repo_root).resolve() / _PROPOSED_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def merge_proposed_env_file(repo_root: Path, updates: dict[str, str]) -> None:
    """Fusiona ``updates`` en ``config/dotenv_wizard_proposed.env`` (no toca ``.env``)."""
    if not updates:
        return
    path = proposed_env_path(repo_root)
    keys_done: set[str] = set()
    new_lines: list[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.strip().startswith("#") or "=" not in line:
                new_lines.append(line)
                continue
            k, _, _ = line.partition("=")
            k = k.strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}")
                keys_done.add(k)
            else:
                new_lines.append(line)
    else:
        new_lines.append(
            "# DuckClaw: .env del repo inmutable — copia manualmente las claves que necesites."
        )
    for key, val in updates.items():
        if key not in keys_done:
            new_lines.append(f"{key}={val}")
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
