"""Equipo /workers y whitelist alineados con Telegram Guard."""

from __future__ import annotations

import os
from typing import Any

from routers.admin_domains.playground.tenant_resolution import (
    gateway_effective_tenant_id,
    playground_telegram_user_id,
)


def playground_team_context(
    *,
    telegram_user_id: str | None = None,
    tenant_id: str | None = None,
    chat_id: str | None = None,
) -> dict[str, Any]:
    """
    Equipo efectivo alineado con ``/workers`` (get_effective_team_templates) y whitelist Telegram.
    En Telegram DM, ``chat_id`` del equipo suele ser el ``user_id`` numérico.
    """
    from duckclaw.gateway_db import GatewayDbEphemeralReadonly, get_gateway_db_path
    from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session
    from duckclaw.graphs.on_the_fly_commands import (
        _get_authorized_role,
        _is_gateway_owner_user,
        get_effective_team_templates,
        get_team_templates,
        get_tenant_team_templates,
    )

    tid = gateway_effective_tenant_id(tenant_id)
    tg_uid = playground_telegram_user_id(telegram_user_id)
    raw_chat = (chat_id or "").strip()
    team_lookup_id = (
        tg_uid
        or (raw_chat if raw_chat and not is_admin_ui_chat_session(raw_chat) else "")
        or "admin-playground"
    )
    team_chat_id = (tg_uid or raw_chat or "admin-playground").strip() or "admin-playground"

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        return {
            "workers": [],
            "telegram_user_id": tg_uid,
            "team_chat_id": team_chat_id,
            "tenant_id": tid,
            "authorized": False,
            "whitelist_role": None,
            "team_source": "none",
            "team_hint": "Gateway DuckDB no encontrada",
        }

    db = GatewayDbEphemeralReadonly(gw)
    role = ""
    authorized = False
    if tg_uid:
        if _is_gateway_owner_user(tg_uid):
            authorized = True
            role = "owner"
        else:
            role = _get_authorized_role(db, tenant_id=tid, user_id=tg_uid)
            authorized = role in ("admin", "user")
    else:
        authorized = True
        role = "admin-ui"

    workers: list[str] = []
    team_source = "none"
    team_hint = ""
    if authorized:
        workers = list(get_effective_team_templates(db, team_lookup_id, tid, None))
        if get_team_templates(db, team_lookup_id):
            team_source = "chat"
            team_hint = "Equipo de este chat (/workers)"
        elif get_tenant_team_templates(db, tid):
            team_source = "tenant"
            team_hint = f"Equipo del tenant «{tid}»"
        elif (os.environ.get("DUCKCLAW_TEAM_MEMBERS") or "").strip():
            team_source = "env"
            team_hint = "Equipo desde variables de entorno (DUCKCLAW_TEAM_MEMBERS)"
        else:
            team_source = "all"
            team_hint = "Sin /workers configurado: todos los templates"

    if tg_uid and not authorized:
        team_hint = (
            f"Usuario Telegram {tg_uid} no está en la whitelist del tenant «{tid}». "
            "Añádelo en Telegram → Whitelist o usa /team en el bot."
        )

    return {
        "workers": workers,
        "telegram_user_id": tg_uid,
        "team_chat_id": team_chat_id,
        "tenant_id": tid,
        "authorized": authorized,
        "whitelist_role": role or None,
        "team_source": team_source,
        "team_hint": team_hint,
    }


def merge_playground_catalog_and_team_workers(
    catalog_workers: list[dict[str, str]],
    team_ctx: dict[str, Any],
) -> list[dict[str, str]]:
    """Admin Playground muestra solo catálogo DB-first; team legacy queda para Telegram."""
    del team_ctx
    return list(catalog_workers)


def playground_worker_allowed_in_team(team_ctx: dict[str, Any], worker_id: str) -> bool:
    from duckclaw.workers.identity import normalize_worker_id
    from duckclaw.workers.template_registry import resolve_template_id_global

    wid = normalize_worker_id(worker_id)
    if not wid or wid == "default":
        return True
    if (team_ctx.get("team_source") or "") == "all":
        return True
    aliases: set[str] = set()
    for raw in team_ctx.get("workers") or []:
        label = str(raw or "").strip()
        if not label:
            continue
        aliases.add(normalize_worker_id(label))
        aliases.add(normalize_worker_id(resolve_template_id_global(label) or label))
    return wid in aliases


def playground_worker_explicitly_in_team(team_ctx: dict[str, Any], worker_id: str) -> bool:
    """Equipo explícito (sin atajo ``team_source=all``) para consola con actor real."""
    from duckclaw.workers.identity import normalize_worker_id
    from duckclaw.workers.template_registry import resolve_template_id_global

    wid = normalize_worker_id(worker_id)
    if not wid or wid == "default":
        return True
    aliases: set[str] = set()
    for raw in team_ctx.get("workers") or []:
        label = str(raw or "").strip()
        if not label:
            continue
        aliases.add(normalize_worker_id(label))
        aliases.add(normalize_worker_id(resolve_template_id_global(label) or label))
    return wid in aliases
