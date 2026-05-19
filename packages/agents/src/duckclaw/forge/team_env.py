"""Equipo y defaults del gateway solo desde variables de entorno (PM2 / .env al arranque).

No lee ``forge/projects/*.yaml`` ni listas de plantillas en el repositorio.
"""

from __future__ import annotations

import os
from typing import Any


def _split_csv(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def team_members_from_env() -> list[str]:
    """Ids de workers del equipo definidos en ``DUCKCLAW_TEAM_MEMBERS``."""
    return _split_csv((os.environ.get("DUCKCLAW_TEAM_MEMBERS") or "").strip())


def load_team_from_env() -> dict[str, Any] | None:
    """
    Metadatos opcionales del equipo en .env (admin / presets).

    Variables: ``DUCKCLAW_TEAM_MEMBERS``, ``DUCKCLAW_TEAM_COORDINATOR``,
    ``DUCKCLAW_TEAM_DISPLAY_NAME``, ``DUCKCLAW_TEAM_ID``, ``DUCKCLAW_TEAM_VAULT_ID``,
    ``DUCKCLAW_TEAM_SHARED_CONTEXT`` / ``_FILE``.
    """
    members = team_members_from_env()
    if not members:
        return None

    team_id = (os.environ.get("DUCKCLAW_TEAM_ID") or "team").strip().lower() or "team"
    display = (os.environ.get("DUCKCLAW_TEAM_DISPLAY_NAME") or team_id).strip()
    coordinator = (os.environ.get("DUCKCLAW_TEAM_COORDINATOR") or "").strip() or None
    vault = (os.environ.get("DUCKCLAW_TEAM_VAULT_ID") or "").strip() or None
    context = os.environ.get("DUCKCLAW_TEAM_SHARED_CONTEXT") or ""
    context_file = (os.environ.get("DUCKCLAW_TEAM_SHARED_CONTEXT_FILE") or "").strip()

    return {
        "id": team_id,
        "slug": team_id,
        "display_name": display,
        "coordinator": coordinator,
        "members": members,
        "shared_vault_id": vault,
        "shared_context": context,
        "shared_context_file": context_file or None,
        "source": "env",
    }


def default_worker_id_from_env() -> str:
    """Worker por defecto: env explícito → primer miembro del equipo → catálogo en disco → ``default``."""
    for key in (
        "DUCKCLAW_DEFAULT_WORKER_ID",
        "DUCKCLAW_TELEGRAM_DEFAULT_WORKER",
    ):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    members = team_members_from_env()
    if members:
        return members[0]
    try:
        from duckclaw.workers.template_registry import list_template_ids

        ids = list_template_ids()
        if "default" in ids:
            return "default"
        return ids[0] if ids else "default"
    except Exception:
        return "default"


def default_tenant_id_from_env() -> str:
    for key in ("DUCKCLAW_GATEWAY_TENANT_ID", "DUCKCLAW_TELEGRAM_DEFAULT_TENANT"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    return "default"
