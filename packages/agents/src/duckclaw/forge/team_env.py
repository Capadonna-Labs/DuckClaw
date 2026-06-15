"""Equipo y defaults administrados del gateway.

No lee ``forge/projects/*.yaml`` ni listas de plantillas en el repositorio.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_DEFAULT_TENANT_ID = "default"
_DEFAULT_TENANT_SETTING_DOMAIN = "gateway"
_DEFAULT_TENANT_SETTING_KEY = "default_tenant_id"


def _split_csv(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def _explicit_default_tenant_id_from_env() -> str:
    for key in ("DUCKCLAW_GATEWAY_TENANT_ID", "DUCKCLAW_TELEGRAM_DEFAULT_TENANT"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    return ""


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
    """
    Tenant por defecto del gateway cuando el cliente envía ``default``.

    Orden: env explícito administrado → ``default``. La identidad de tenant no se
    infiere desde nombres de proceso, rutas de base de datos ni layouts locales.
    """
    return _explicit_default_tenant_id_from_env() or _DEFAULT_TENANT_ID


def _default_tenant_id_from_runtime_settings() -> str:
    try:
        from duckclaw import DuckClaw
        from duckclaw.admin_runtime_settings import resolve_runtime_setting
        from duckclaw.gateway_db import get_gateway_db_path

        db_path = (get_gateway_db_path() or "").strip()
        if not db_path or not Path(db_path).is_file():
            return ""
        db = DuckClaw(db_path, read_only=True, engine="python")
        try:
            resolved = resolve_runtime_setting(
                db,
                tenant_id="global",
                actor_email="",
                domain=_DEFAULT_TENANT_SETTING_DOMAIN,
                key=_DEFAULT_TENANT_SETTING_KEY,
                default="",
            )
        finally:
            db.close()
    except Exception:
        return ""
    return str(resolved.get("value") or "").strip()


def default_tenant_id_from_runtime() -> str:
    """
    Tenant default administrado para gateway/Telegram.

    Orden: env explícito administrado → ``admin_runtime_settings`` global
    (``gateway.default_tenant_id``) → fallback seguro ``default``. Nunca infiere
    desde PM2, rutas DuckDB ni layouts locales, y solo abre el hub en read-only.
    """
    return (
        _explicit_default_tenant_id_from_env()
        or _default_tenant_id_from_runtime_settings()
        or _DEFAULT_TENANT_ID
    )
