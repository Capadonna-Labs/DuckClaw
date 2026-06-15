"""Team template command ownership for chat and tenant runtime state."""

from __future__ import annotations

import json
import os
from typing import Any, Optional, Protocol

from duckclaw.commands.chat_state import (
    get_chat_state,
    get_global_config as _get_global_config,
    set_chat_state,
    set_global_config as _set_global_config,
)
from duckclaw.guardrails.loader import load_guardrail


class TeamAdminChecker(Protocol):
    def __call__(self, db: Any, *, tenant_id: str, requester_id: str) -> bool: ...


_team_admin_checker: TeamAdminChecker | None = None
_TENANT_TEAM_KEY_PREFIX = "tenant_team:"


def configure_team_template_admin_checker(checker: TeamAdminChecker | None) -> None:
    """Attach the graph-owned admin predicate without moving whitelist ownership here."""
    global _team_admin_checker
    _team_admin_checker = checker


def get_team_templates(db: Any, chat_id: Any) -> list:
    """Templates disponibles en el equipo para este chat. Vacío = todos los de list_workers()."""
    raw = get_chat_state(db, chat_id, "team_templates")
    if not raw:
        return []
    try:
        out = json.loads(raw)
        return out if isinstance(out, list) else []
    except Exception:
        return []


def set_team_templates(db: Any, chat_id: Any, template_ids: list) -> None:
    """Define los templates del equipo para este chat. Lista vacía = usar todos."""
    set_chat_state(db, chat_id, "team_templates", json.dumps([str(x).strip() for x in template_ids]))


def _tenant_team_config_key(tenant_id: Any) -> str:
    tid = str(tenant_id or "default").strip() or "default"
    return f"{_TENANT_TEAM_KEY_PREFIX}{tid}"


def get_tenant_team_templates(db: Any, tenant_id: Any) -> list:
    """Equipo por defecto para todo el tenant. Vacío = no hay override a nivel tenant."""
    raw = _get_global_config(db, _tenant_team_config_key(tenant_id))
    if not raw:
        return []
    try:
        out = json.loads(raw)
        return out if isinstance(out, list) else []
    except Exception:
        return []


def set_tenant_team_templates(db: Any, tenant_id: Any, template_ids: list) -> None:
    """Persiste el equipo default del tenant en agent_config."""
    _set_global_config(
        db,
        _tenant_team_config_key(tenant_id),
        json.dumps([str(x).strip() for x in template_ids]),
    )


def _canonicalize_team_template_ids(ids: list, templates_root: Any = None) -> list:
    """Resuelve alias de manifest y descarta ids sin template local."""
    from duckclaw.workers.template_registry import list_template_ids, resolve_template_id

    all_t = list_template_ids(templates_root)
    out: list[str] = []
    seen: set[str] = set()
    for raw in ids or []:
        w = str(raw or "").strip()
        if not w:
            continue
        canonical = resolve_template_id(all_t, w)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        out.append(canonical)
    return out


def get_effective_team_templates(
    db: Any, chat_id: Any, tenant_id: Any, templates_root: Any = None
) -> list:
    """
    Equipo que ve el manager para delegar, en orden:
    1) team_templates del chat
    2) team_templates del tenant
    3) DUCKCLAW_TEAM_MEMBERS
    4) todos los templates
    """
    from duckclaw.workers.factory import list_workers

    chat_team = get_team_templates(db, chat_id)
    if chat_team:
        return _canonicalize_team_template_ids(chat_team, templates_root)
    tid = str(tenant_id or "default").strip() or "default"
    tenant_team = get_tenant_team_templates(db, tid)
    if tenant_team:
        return _canonicalize_team_template_ids(tenant_team, templates_root)
    env_raw = (os.environ.get("DUCKCLAW_TEAM_MEMBERS") or "").strip()
    if env_raw:
        all_t = list_workers(templates_root)
        out: list[str] = []
        for part in env_raw.split(","):
            p = part.strip()
            if not p:
                continue
            c = _resolve_template_id(all_t, p)
            if c:
                out.append(c)
        if out:
            return out
    return list_workers(templates_root)


def _sync_tenant_team_if_admin(
    db: Any,
    *,
    tenant_id: Any,
    requester_id: Any,
    template_ids: list,
) -> None:
    """Replica el equipo del chat como default del tenant cuando el grafo confirma admin."""
    tid = str(tenant_id or "").strip()
    rid = str(requester_id or "").strip()
    if not tid or not rid or _team_admin_checker is None:
        return
    if not _team_admin_checker(db, tenant_id=tid, requester_id=rid):
        return
    set_tenant_team_templates(db, tid, template_ids)


def _resolve_template_id(available: list, user_input: str) -> Optional[str]:
    """Resuelve alias de manifest al id canónico de template."""
    from duckclaw.workers.template_registry import resolve_template_id

    return resolve_template_id(available, user_input)


def execute_team(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: Any = None,
    requester_id: Any = None,
) -> str:
    """/workers [id1 id2 ...] [--add id...] [--rm worker_id]: equipo del chat."""
    from duckclaw.workers.factory import list_workers

    all_templates = list_workers()
    tid = str(tenant_id or "default").strip() or "default"
    team = get_team_templates(db, chat_id)
    if not args or not args.strip():
        effective = get_effective_team_templates(db, chat_id, tid, None)
        if not effective:
            return "No hay templates disponibles. Añade al menos uno al catálogo."
        if team:
            label = "Equipo (este chat):"
        elif get_tenant_team_templates(db, tid):
            label = "Equipo del tenant (todos los chats sin override):"
        elif (os.environ.get("DUCKCLAW_TEAM_MEMBERS") or "").strip():
            label = "Equipo (.env):"
        else:
            label = "Equipo: todos los templates"
        lines = "\n".join(f"- {w}" for w in effective)
        hint = load_guardrail("fly_commands", "workers_list_hint")
        return f"🦆 {label}\n{lines}\n\n{hint}"
    raw = args.strip()
    if raw.startswith("--rm "):
        wid_raw = raw[5:].strip().split()[0]
        canonical = _resolve_template_id(all_templates, wid_raw)
        if not canonical:
            return f"'{wid_raw}' no es un template. Equipo actual: {', '.join(team or all_templates) or 'todos'}"
        current = team if team else list(all_templates)
        new_team = [x for x in current if (x or "").strip().lower() != canonical.lower()]
        if len(new_team) == len(current):
            return f"'{canonical}' no está en el equipo. Equipo actual: {', '.join(current) or 'todos'}"
        set_team_templates(db, chat_id, new_team)
        _sync_tenant_team_if_admin(
            db, tenant_id=tid, requester_id=requester_id, template_ids=new_team
        )
        return f"✅ Quitado {canonical} del equipo. Quedan: {', '.join(new_team) or 'ninguno (el manager usará todos)'}."
    if raw.startswith("--add ") or raw.strip() == "--add":
        ids_str = raw[6:].strip() if raw.startswith("--add ") else ""
        ids_raw = [x.strip() for x in ids_str.split() if x.strip()]
        valid = []
        invalid = []
        for i in ids_raw:
            c = _resolve_template_id(all_templates, i)
            if c:
                valid.append(c)
            else:
                invalid.append(i)
        if invalid:
            return f"Templates no encontrados: {', '.join(invalid)}. Disponibles: {', '.join(all_templates)}"
        current = list(team) if team else list(all_templates)
        for c in valid:
            if not any((x or "").strip().lower() == c.lower() for x in current):
                current.append(c)
        set_team_templates(db, chat_id, current)
        _sync_tenant_team_if_admin(
            db, tenant_id=tid, requester_id=requester_id, template_ids=current
        )
        return f"✅ Añadidos al equipo: {', '.join(valid)}. Equipo: {', '.join(current)}."
    ids_raw = [x.strip() for x in raw.split() if x.strip()]
    valid = []
    invalid = []
    for i in ids_raw:
        c = _resolve_template_id(all_templates, i)
        if c:
            valid.append(c)
        else:
            invalid.append(i)
    if invalid:
        return f"Templates no encontrados: {', '.join(invalid)}. Disponibles: {', '.join(all_templates)}"
    set_team_templates(db, chat_id, valid)
    _sync_tenant_team_if_admin(db, tenant_id=tid, requester_id=requester_id, template_ids=valid)
    return f"✅ Equipo de este chat: {', '.join(valid)}. El manager delegará solo a estos."
