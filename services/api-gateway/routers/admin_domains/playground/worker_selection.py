"""Selección de worker y opciones de vault para admin playground."""

from __future__ import annotations

import re
from typing import Any

from routers.admin_domains.playground.tenant_resolution import playground_telegram_user_id


def iter_template_ids_for_catalog() -> list[str]:
    from duckclaw.workers.template_registry import list_template_ids

    return list_template_ids()


def pick_playground_worker(
    team_ctx: dict[str, Any],
    worker_id: str | None = None,
    *,
    require_browser_sandbox: bool = False,
) -> str:
    """Primer worker del equipo, del catálogo en disco, o ``default``."""
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", (worker_id or "").strip())
    if wid:
        return wid
    team = [w for w in (team_ctx.get("workers") or []) if isinstance(w, str) and w.strip()]
    if require_browser_sandbox:
        from routers.admin_domains.sandbox_sessions import _worker_has_browser_sandbox

        for candidate in team:
            if _worker_has_browser_sandbox(candidate):
                return candidate
        for candidate in iter_template_ids_for_catalog():
            if _worker_has_browser_sandbox(candidate):
                return candidate
    elif team:
        return team[0].strip()
    catalog = iter_template_ids_for_catalog()
    if "default" in catalog:
        return "default"
    return catalog[0] if catalog else "default"


def playground_vault_options_for_team(team_ctx: dict[str, Any]) -> list[dict[str, str]]:
    from duckclaw.vaults import list_vault_options_for_user

    uid = str(team_ctx.get("telegram_user_id") or "").strip()
    if not uid:
        uid = playground_telegram_user_id(None) or "default"
    return list_vault_options_for_user(uid)
