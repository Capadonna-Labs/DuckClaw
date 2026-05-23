"""
Perfil Spawn (VM genérica sin DB-Writer en PM2).

Cuando ``DUCKCLAW_SPAWN_PROFILE`` está activo y no hay escape hatch
``DUCKCLAW_SPAWN_USE_DB_WRITER=1``, el gateway/graph deben abrir el hub DuckDB
en lectura-escritura y aplicar mutaciones en proceso (sin colas Redis huérfanas).

Spec: specs/features/platform/SPAWN_GENERIC_DEPLOY.md
"""

from __future__ import annotations

import os

_SPAWN_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in _SPAWN_TRUTHY


def is_spawn_profile() -> bool:
    """True si la VM/perfil Spawn está activo (``DUCKCLAW_SPAWN_PROFILE``)."""
    return _env_truthy("DUCKCLAW_SPAWN_PROFILE")


def spawn_inline_writes_enabled() -> bool:
    """
    Escrituras DuckDB en el mismo proceso que el gateway (sin db-writer).

    Desactivar solo si se arranca explícitamente el proceso ``DuckClaw-DB-Writer``.
    """
    return is_spawn_profile() and not _env_truthy("DUCKCLAW_SPAWN_USE_DB_WRITER")
