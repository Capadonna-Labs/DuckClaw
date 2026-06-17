"""Intento de Redis local gestionado (spec §5 — brew / apt)."""

from __future__ import annotations

from pathlib import Path


def try_start_redis_local(repo_root: Path) -> tuple[bool, str]:
    """
    macOS: ``brew install redis`` + ``brew services start redis`` si hace falta.
    Linux: ``apt install redis-server`` + systemctl (sudo).
    """
    from duckops.prerequisites import check_redis, install_redis

    if check_redis().ok:
        return True, "Redis ya responde en localhost."
    ok = install_redis(print_fn=lambda m: None, assume_yes=True)
    if ok and check_redis().ok:
        return True, "Redis instalado y en marcha."
    return (
        ok,
        "No se pudo instalar/arrancar Redis automáticamente. "
        "Ejecuta: duckops bootstrap --yes",
    )
