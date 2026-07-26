"""
Perfil Spawn (VM genérica sin DB-Writer en PM2).

Cuando ``DUCKCLAW_SPAWN_PROFILE`` está activo y no hay escape hatch
``DUCKCLAW_SPAWN_USE_DB_WRITER=1``, el gateway/graph deben abrir el hub DuckDB
en lectura-escritura y aplicar mutaciones en proceso (sin colas Redis huérfanas).

Desktop lite: ``LITE_MODE=1`` es alias de Spawn (ver DESKTOP_LITE_SIDECAR.md).

Spec: docs/GETTING_STARTED.md
"""

from __future__ import annotations

import os

_SPAWN_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in _SPAWN_TRUTHY


def is_lite_mode() -> bool:
    """True when ``LITE_MODE`` is set (desktop sidecar alias for Spawn inline)."""
    return _env_truthy("LITE_MODE")


def apply_lite_mode_env() -> None:
    """Map ``LITE_MODE=1`` → Spawn inline profile. Idempotent; call before gateway bootstrap."""
    if not is_lite_mode():
        return
    os.environ.setdefault("DUCKCLAW_SPAWN_PROFILE", "1")
    os.environ.pop("DUCKCLAW_SPAWN_USE_DB_WRITER", None)


def is_spawn_profile() -> bool:
    """True si la VM/perfil Spawn está activo (``DUCKCLAW_SPAWN_PROFILE``)."""
    apply_lite_mode_env()
    return _env_truthy("DUCKCLAW_SPAWN_PROFILE")


def spawn_inline_writes_enabled() -> bool:
    """
    Escrituras DuckDB en el mismo proceso que el gateway (sin db-writer).

    Desactivar solo si se arranca explícitamente el proceso ``DuckClaw-DB-Writer``.
    """
    apply_lite_mode_env()
    return is_spawn_profile() and not _env_truthy("DUCKCLAW_SPAWN_USE_DB_WRITER")


def effective_hub_read_only(db_path: str, read_only: bool) -> bool:
    """ponytail: spawn/lite hub must share one RW DuckDB config in-process."""
    if not read_only:
        return False
    if not spawn_inline_writes_enabled():
        return True
    from duckclaw.gateway_db import get_gateway_db_path

    gw = (get_gateway_db_path() or "").strip()
    if not gw:
        return True
    try:
        if os.path.normcase(os.path.abspath(db_path)) == os.path.normcase(os.path.abspath(gw)):
            return False
    except OSError:
        pass
    return True
