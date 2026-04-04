"""
On-the-Fly CLI: comandos de Telegram que mutan estado del grafo sin reiniciar.

Spec: specs/interfaz_de_comandos_dinamicos_On-the-Fly_CLI.md
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional, Tuple
from duckclaw.vaults import (
    create_vault as _vault_create,
    list_vaults as _vault_list,
    remove_vault as _vault_remove,
    resolve_active_vault as _vault_resolve_active,
    switch_vault as _vault_switch,
    validate_user_db_path,
    vault_scope_id_for_tenant,
)

from duckclaw.forge.skills.the_mind_outbound import (
    broadcast_message_to_players,
    deal_cards_for_level,
    send_telegram_dm,
)
from duckclaw.utils.logger import get_obs_logger, log_fly, structured_log_context
from duckclaw.utils.telegram_markdown_v2 import TELEGRAM_MARKDOWN_V2_SPECIAL

_PREFIX = "chat_"


def _skip_runtime_ddl(db: Any) -> bool:
    """Si True, no ejecutar CREATE/ALTER en runtime (asumir scripts/bootstrap_dbs.py)."""
    return bool(getattr(db, "_read_only", False))


def unescape_telegram_markdown_v2_layers(text: str, max_layers: int = 4) -> str:
    """
    Quita hasta ``max_layers`` capas de escape estilo MarkdownV2 (mismo juego de
    caracteres que ``escape_telegram_markdown_v2``). Sirve para:

    - Historial que reinyecta la respuesta HTTP ya escapada (n8n / cliente).
    - Salidas del modelo que copian ``\\.``, ``\\!``, ``\\*`` del contexto.

    Sin esto, el escape MDV2 vuelve a escapar las barras y el texto crece
    (p. ej. ``\\!`` → ``\\\\!`` → ``\\\\\\!``).
    """
    if not text:
        return ""
    esc = frozenset(TELEGRAM_MARKDOWN_V2_SPECIAL)
    t = str(text)
    for _ in range(max(1, int(max_layers))):
        out: list[str] = []
        i = 0
        while i < len(t):
            if t[i] == "\\" and i + 1 < len(t) and t[i + 1] in esc:
                out.append(t[i + 1])
                i += 2
            else:
                out.append(t[i])
                i += 1
        t_new = "".join(out)
        if t_new == t:
            return t_new
        t = t_new
    return t


def _chat_key(chat_id: Any, suffix: str) -> str:
    """Key for agent_config; supports numeric (Telegram) and string (API session_id)."""
    try:
        cid = int(chat_id)
        return f"{_PREFIX}{cid}_{suffix}"
    except (TypeError, ValueError):
        return f"{_PREFIX}{str(chat_id)[:64]}_{suffix}"


_AGENT_CONFIG_TABLE = "agent_config"

# Telegram Guard whitelist persistence (DuckDB table in schema `main`)
_AUTHORIZED_USERS_TABLE = "authorized_users"
_AUTHORIZED_USERS_DDL = f"""
CREATE TABLE IF NOT EXISTS main.{_AUTHORIZED_USERS_TABLE} (
    tenant_id VARCHAR,
    user_id VARCHAR,
    username VARCHAR,
    role VARCHAR DEFAULT 'user',
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, user_id)
);
"""


def _sql_escape_literal(v: Any, max_len: int = 256) -> str:
    s = "" if v is None else str(v)
    return s.replace("'", "''")[:max_len]


def _ensure_authorized_users_table(db: Any) -> None:
    try:
        db.execute(_AUTHORIZED_USERS_DDL)
    except Exception:
        # Best-effort: si falla, la whitelist mutación/consulta se comportará como “no autorizado”.
        pass


def _is_gateway_owner_user(user_id: str) -> bool:
    """Coincide con el bypass del API Gateway (DUCKCLAW_OWNER_ID / DUCKCLAW_ADMIN_CHAT_ID)."""
    uid = str(user_id or "").strip()
    if not uid:
        return False
    owner = (os.environ.get("DUCKCLAW_OWNER_ID") or os.environ.get("DUCKCLAW_ADMIN_CHAT_ID") or "").strip()
    return bool(owner and uid == owner)


def _is_team_admin(db: Any, *, tenant_id: str, requester_id: str) -> bool:
    if _is_gateway_owner_user(requester_id):
        return True
    return _get_authorized_role(db, tenant_id=tenant_id, user_id=requester_id) == "admin"


def _get_authorized_role(db: Any, *, tenant_id: str, user_id: str) -> str:
    _ensure_authorized_users_table(db)
    tid = _sql_escape_literal(tenant_id, max_len=128)
    uid = _sql_escape_literal(user_id, max_len=128)
    try:
        raw = db.query(
            f"SELECT role FROM main.{_AUTHORIZED_USERS_TABLE} "
            f"WHERE lower(tenant_id)=lower('{tid}') AND user_id='{uid}' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            return (rows[0].get("role") or "").strip().lower()
    except Exception:
        pass
    return ""


def _list_authorized_users(db: Any, *, tenant_id: str) -> list[dict[str, str]]:
    _ensure_authorized_users_table(db)
    tid = _sql_escape_literal(tenant_id, max_len=128)
    try:
        raw = db.query(
            f"SELECT user_id, username, role FROM main.{_AUTHORIZED_USERS_TABLE} "
            f"WHERE lower(tenant_id)=lower('{tid}') ORDER BY user_id"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if isinstance(rows, list):
            out: list[dict[str, str]] = []
            for r in rows:
                if isinstance(r, dict):
                    out.append(
                        {
                            "user_id": str(r.get("user_id") or "").strip(),
                            "username": str(r.get("username") or "").strip(),
                            "role": str(r.get("role") or "").strip(),
                        }
                    )
            return out
    except Exception as exc:
        logging.getLogger("duckclaw.team_whitelist").warning(
            "authorized_users list query failed tenant_id=%r: %s", tenant_id, exc
        )
    return []


def _dedupe_authorized_users_by_user_id(users: list[dict[str, str]]) -> list[dict[str, str]]:
    """
    Unifica filas por ``user_id`` (p. ej. duplicados legacy por distinto casing de ``tenant_id`` en PK).
    Si hay varias filas, se prioriza la que tenga rol ``admin``.
    """
    rank = {"admin": 3, "user": 2, "operator": 2, "observer": 1}

    def _score(u: dict[str, str]) -> int:
        r = (u.get("role") or "").strip().lower()
        return int(rank.get(r, 2))

    best: dict[str, dict[str, str]] = {}
    for u in users:
        uid = str(u.get("user_id") or "").strip()
        if not uid:
            continue
        if uid not in best or _score(u) > _score(best[uid]):
            best[uid] = u
    out = list(best.values())
    out.sort(key=lambda x: str(x.get("user_id") or ""))
    return out


def _upsert_authorized_user(db: Any, *, tenant_id: str, user_id: str, username: str, role: str = "user") -> None:
    _ensure_authorized_users_table(db)
    tid = _sql_escape_literal(tenant_id, max_len=128)
    uid = _sql_escape_literal(user_id, max_len=128)
    un = _sql_escape_literal(username or "Usuario", max_len=128)
    rl = _sql_escape_literal(role or "user", max_len=16)
    db.execute(
        f"""
        INSERT INTO main.{_AUTHORIZED_USERS_TABLE} (tenant_id, user_id, username, role)
        VALUES ('{tid}', '{uid}', '{un}', '{rl}')
        ON CONFLICT (tenant_id, user_id) DO UPDATE SET
          username = EXCLUDED.username,
          role = EXCLUDED.role,
          added_at = now()
        """
    )


def _delete_authorized_user(db: Any, *, tenant_id: str, user_id: str) -> None:
    _ensure_authorized_users_table(db)
    tid = _sql_escape_literal(tenant_id, max_len=128)
    uid = _sql_escape_literal(user_id, max_len=128)
    db.execute(
        f"DELETE FROM main.{_AUTHORIZED_USERS_TABLE} "
        f"WHERE lower(tenant_id)=lower('{tid}') AND user_id='{uid}'"
    )


def _is_wr_tenant(tenant_id: str | None) -> bool:
    return str(tenant_id or "").strip().lower().startswith("wr_")


def _ensure_war_room_tables(db: Any) -> None:
    try:
        db.execute("CREATE SCHEMA IF NOT EXISTS war_room_core;")
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS war_room_core.wr_members (
                tenant_id VARCHAR,
                user_id VARCHAR,
                username VARCHAR,
                clearance_level VARCHAR,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (tenant_id, user_id)
            );
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS war_room_core.wr_audit_log (
                event_id VARCHAR PRIMARY KEY,
                tenant_id VARCHAR,
                sender_id VARCHAR,
                target_agent VARCHAR,
                event_type VARCHAR,
                payload TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
    except Exception:
        pass


def _wr_member_clearance(db: Any, *, tenant_id: str, user_id: str) -> str:
    _ensure_war_room_tables(db)
    tid = _sql_escape_literal(tenant_id, max_len=128)
    uid = _sql_escape_literal(user_id, max_len=128)
    try:
        raw = db.query(
            "SELECT clearance_level FROM war_room_core.wr_members "
            f"WHERE lower(tenant_id)=lower('{tid}') AND user_id='{uid}' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            return str(rows[0].get("clearance_level") or "").strip().lower()
    except Exception:
        pass
    return ""


def _wr_append_audit(
    db: Any,
    *,
    tenant_id: str,
    sender_id: str,
    target_agent: str,
    event_type: str,
    payload: str,
) -> None:
    import uuid

    _ensure_war_room_tables(db)
    db.execute(
        "INSERT INTO war_room_core.wr_audit_log (event_id, tenant_id, sender_id, target_agent, event_type, payload) "
        f"VALUES ('{uuid.uuid4()}', '{_sql_escape_literal(tenant_id, 128)}', "
        f"'{_sql_escape_literal(sender_id, 128)}', '{_sql_escape_literal(target_agent, 64)}', "
        f"'{_sql_escape_literal(event_type, 64)}', '{_sql_escape_literal(payload, 8000)}')"
    )


def register_wr_member(db: Any, tenant_id: Any, requester_id: Any, args: str) -> str:
    tid = str(tenant_id or "default").strip() or "default"
    rid = str(requester_id or "").strip()
    if not _is_wr_tenant(tid):
        return "register_wr_member solo aplica en tenants War Room (wr_<group_id>)."
    _ensure_war_room_tables(db)
    clearance = _wr_member_clearance(db, tenant_id=tid, user_id=rid)
    if not (_is_gateway_owner_user(rid) or clearance == "admin"):
        return "❌ Acceso denegado: solo admin WR puede registrar miembros."
    tokens = [x for x in (args or "").split() if x.strip()]
    if len(tokens) < 2:
        return "Uso: /register_wr_member <user_id> <clearance> [username]"
    uid = tokens[0].strip()
    clr = tokens[1].strip().lower()
    uname = " ".join(tokens[2:]).strip() or "Usuario"
    if clr not in ("admin", "operator", "observer"):
        return "clearance inválido. Usa: admin | operator | observer"
    db.execute(
        "INSERT INTO war_room_core.wr_members (tenant_id, user_id, username, clearance_level) "
        f"VALUES ('{_sql_escape_literal(tid, 128)}', '{_sql_escape_literal(uid, 128)}', "
        f"'{_sql_escape_literal(uname, 128)}', '{_sql_escape_literal(clr, 32)}') "
        "ON CONFLICT (tenant_id, user_id) DO UPDATE SET username=EXCLUDED.username, clearance_level=EXCLUDED.clearance_level, added_at=now()"
    )
    _wr_append_audit(
        db,
        tenant_id=tid,
        sender_id=rid,
        target_agent="manager",
        event_type="REGISTER_WR_MEMBER",
        payload=f"user_id={uid} clearance={clr}",
    )
    return f"✅ Miembro WR registrado: {uid} ({clr})."


def get_wr_context(db: Any, tenant_id: Any, args: str) -> str:
    tid = str(tenant_id or "default").strip() or "default"
    if not _is_wr_tenant(tid):
        return "get_wr_context solo aplica en tenants War Room (wr_<group_id>)."
    _ensure_war_room_tables(db)
    minutes = 60
    try:
        if (args or "").strip():
            minutes = max(1, min(1440, int((args or "").strip())))
    except ValueError:
        minutes = 60
    raw = db.query(
        "SELECT sender_id, target_agent, event_type, payload, timestamp "
        "FROM war_room_core.wr_audit_log "
        f"WHERE lower(tenant_id)=lower('{_sql_escape_literal(tid, 128)}') "
        f"AND timestamp >= now() - INTERVAL '{minutes} minutes' "
        "ORDER BY timestamp DESC LIMIT 10"
    )
    rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    if not rows:
        return "Sin eventos recientes en wr_audit_log."
    lines = ["🧭 War Room Context (últimos eventos):"]
    for r in rows:
        if not isinstance(r, dict):
            continue
        lines.append(
            f"- [{r.get('timestamp')}] {r.get('event_type')} by {r.get('sender_id')} -> {r.get('target_agent')}: {str(r.get('payload') or '')[:120]}"
        )
    return "\n".join(lines)


def broadcast_alert(db: Any, tenant_id: Any, requester_id: Any, args: str) -> str:
    tid = str(tenant_id or "default").strip() or "default"
    rid = str(requester_id or "").strip()
    if not _is_wr_tenant(tid):
        return "broadcast_alert solo aplica en tenants War Room (wr_<group_id>)."
    parts = [x.strip() for x in (args or "").split(None, 1) if x.strip()]
    if len(parts) < 2:
        return "Uso: /broadcast_alert <level> <message>"
    level, message = parts[0].lower(), parts[1]
    if level not in ("info", "warn", "critical"):
        return "level inválido. Usa: info | warn | critical"
    _wr_append_audit(
        db,
        tenant_id=tid,
        sender_id=rid or "system",
        target_agent="group",
        event_type="BROADCAST_ALERT",
        payload=f"[{level}] {message}",
    )
    return f"🚨 WR alert ({level}) registrada."


def _invalidate_whitelist_redis_cache(*, tenant_id: str, user_id: str) -> None:
    """
    El Gateway cachea roles en Redis (TTL ~1h). Tras /team --rm o --add, hay que borrar la clave
    o los usuarios revocados siguen pasando _lookup_whitelist_role hasta que expire el TTL.
    Misma convención que services/api-gateway/main.py: whitelist:{tenant_lower}:{user_id}
    """
    tid = str(tenant_id or "default").strip().lower() or "default"
    uid = str(user_id or "").strip()
    if not uid:
        return
    url = (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    if not url:
        return
    key = f"whitelist:{tid}:{uid}"
    try:
        import redis as redis_sync  # noqa: PLC0415

        client = redis_sync.Redis.from_url(url, decode_responses=True)
        client.delete(key)
    except Exception:
        pass


def _invalidate_wr_clearance_redis_cache(*, tenant_id: str, user_id: str) -> None:
    """Invalidar cache de clearance WR (services/api-gateway/main.py::_lookup_wr_clearance)."""
    tid = str(tenant_id or "default").strip().lower() or "default"
    uid = str(user_id or "").strip()
    if not uid:
        return
    url = (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    if not url:
        return
    key = f"wr_clearance:{tid}:{uid}"
    try:
        import redis as redis_sync  # noqa: PLC0415

        client = redis_sync.Redis.from_url(url, decode_responses=True)
        client.delete(key)
    except Exception:
        pass


def _ensure_agent_config(db: Any) -> None:
    if _skip_runtime_ddl(db):
        return
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_AGENT_CONFIG_TABLE} (
            key VARCHAR PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def get_chat_state(db: Any, chat_id: Any, key: str) -> str:
    """Read a chat-scoped config key from agent_config."""
    _ensure_agent_config(db)
    k = _chat_key(chat_id, key).replace("'", "''")[:200]
    try:
        r = db.query(f"SELECT value FROM {_AGENT_CONFIG_TABLE} WHERE key = '{k}' LIMIT 1")
        rows = json.loads(r) if isinstance(r, str) else (r or [])
        if rows and isinstance(rows[0], dict):
            return (rows[0].get("value") or "").strip()
    except Exception:
        pass
    return ""


def set_chat_state(db: Any, chat_id: Any, key: str, value: str) -> None:
    """Write a chat-scoped config key to agent_config."""
    _ensure_agent_config(db)
    k = _chat_key(chat_id, key).replace("'", "''")[:128]
    v = str(value).replace("'", "''")[:16384]
    db.execute(
        f"""
        INSERT INTO {_AGENT_CONFIG_TABLE} (key, value) VALUES ('{k}', '{v}')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """
    )


def parse_command(text: str) -> Tuple[str, str]:
    """Parse /command or /command args. Returns (name, args)."""
    if not text or not text.strip().startswith("/"):
        return "", ""
    parts = text.strip().split(maxsplit=1)
    name = (parts[0] or "").lstrip("/").lower()
    args = (parts[1] if len(parts) > 1 else "").strip()
    return name, args


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
    """Define los templates del equipo para este chat. Lista vacía = usar todos (list_workers). Guarda ids canónicos (case del filesystem)."""
    set_chat_state(db, chat_id, "team_templates", json.dumps([str(x).strip() for x in template_ids]))


_TENANT_TEAM_KEY_PREFIX = "tenant_team:"


def _tenant_team_config_key(tenant_id: Any) -> str:
    tid = str(tenant_id or "default").strip() or "default"
    return f"{_TENANT_TEAM_KEY_PREFIX}{tid}"


def get_tenant_team_templates(db: Any, tenant_id: Any) -> list:
    """Equipo por defecto para todo el tenant (misma DuckDB compartida). Vacío = no hay override a nivel tenant."""
    raw = _get_global_config(db, _tenant_team_config_key(tenant_id))
    if not raw:
        return []
    try:
        out = json.loads(raw)
        return out if isinstance(out, list) else []
    except Exception:
        return []


def set_tenant_team_templates(db: Any, tenant_id: Any, template_ids: list) -> None:
    """Persiste el equipo default del tenant en agent_config (clave global)."""
    _set_global_config(
        db,
        _tenant_team_config_key(tenant_id),
        json.dumps([str(x).strip() for x in template_ids]),
    )


def get_effective_team_templates(
    db: Any, chat_id: Any, tenant_id: Any, templates_root: Any = None
) -> list:
    """
    Equipo que ve el manager para delegar, en orden:
    1) team_templates del chat
    2) team_templates del tenant (admin vía /workers)
    3) DUCKCLAW_GATEWAY_TEAM_TEMPLATES (coma-separado, ids canónicos tras resolver)
    4) todos los templates (list_workers)
    """
    from duckclaw.workers.factory import list_workers

    chat_team = get_team_templates(db, chat_id)
    if chat_team:
        return list(chat_team)
    tid = str(tenant_id or "default").strip() or "default"
    tenant_team = get_tenant_team_templates(db, tid)
    if tenant_team:
        return list(tenant_team)
    env_raw = (os.environ.get("DUCKCLAW_GATEWAY_TEAM_TEMPLATES") or "").strip()
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
    """Si el requester es admin del tenant, replica el equipo del chat como default del tenant."""
    tid = str(tenant_id or "").strip()
    rid = str(requester_id or "").strip()
    if not tid or not rid:
        return
    if not _is_team_admin(db, tenant_id=tid, requester_id=rid):
        return
    set_tenant_team_templates(db, tid, template_ids)


def _resolve_template_id(available: list, user_input: str) -> Optional[str]:
    """Resuelve el input del usuario (p. ej. 'themindcrupier') al id canónico del template (p. ej. 'ThemindCrupier'). Case-insensitive."""
    if not available or not (user_input or "").strip():
        return None
    key = (user_input or "").strip().lower()
    for a in available:
        if (a or "").strip().lower() == key:
            return (a or "").strip()
    return None


def execute_team(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: Any = None,
    requester_id: Any = None,
) -> str:
    """/workers [id1 id2 ...] [--add id...] [--rm worker_id]: equipo del chat. Sin args: lista. Con ids: reemplaza. --add: añade; --rm: quita uno. Admin: también actualiza el equipo default del tenant."""
    from duckclaw.workers.factory import list_workers
    all_templates = list_workers()
    tid = str(tenant_id or "default").strip() or "default"
    team = get_team_templates(db, chat_id)
    if not args or not args.strip():
        effective = get_effective_team_templates(db, chat_id, tid, None)
        if not effective:
            return "No hay templates en forge/templates. Añade al menos uno."
        if team:
            label = "Equipo (este chat):"
        elif get_tenant_team_templates(db, tid):
            label = "Equipo del tenant (todos los chats sin override):"
        elif (os.environ.get("DUCKCLAW_GATEWAY_TEAM_TEMPLATES") or "").strip():
            label = "Equipo (DUCKCLAW_GATEWAY_TEAM_TEMPLATES):"
        else:
            label = "Equipo: todos los templates"
        lines = "\n".join(f"- {w}" for w in effective)
        hint = (
            "Reemplazar: /workers id1 id2 | Añadir: /workers --add id | Quitar: /workers --rm id | Ver todos: /roles"
        )
        return f"🦆 {label}\n{lines}\n\n{hint}"
    raw = args.strip()
    # --rm <worker_id>
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
    # --add id1 id2 ... (insert/appendix al equipo actual)
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
    # id1 id2 ... → reemplazar equipo
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


def _dedicated_gateway_db_path_for_vault() -> str | None:
    """
    Misma regla que el API Gateway: api_gateways_pm2.json + claves multiplex / DUCKDB_PATH
    (evita /vault y fly mostrando finanzdb1 del registry en gateways dedicados).
    """
    from duckclaw.pm2_gateway_db import dedicated_gateway_db_path_resolved

    return dedicated_gateway_db_path_resolved()


def _session_duckdb_path_for_fly(db: Any) -> str | None:
    """Ruta del ``DuckClaw``/sesión que abrió el gateway para el turno (multiplex por bot)."""
    p = getattr(db, "_path", None)
    if p is None:
        return None
    s = str(p).strip()
    if not s or s == ":memory:":
        return None
    try:
        from pathlib import Path as _P

        return str(_P(s).expanduser().resolve())
    except Exception:
        return None


def _fly_vault_label_for_tenant(tenant_id: Any) -> str:
    tid = str(tenant_id or "").strip()
    if not tid or tid.lower() == "default":
        return _dedicated_gateway_vault_label()
    pretty = {
        "Finanzas": "Finanz",
        "SIATA": "SIATA Analyst",
        "Trabajo": "Job Hunter",
    }
    return pretty.get(tid, tid)


def _dedicated_gateway_vault_label() -> str:
    proc = (os.environ.get("DUCKCLAW_PM2_PROCESS_NAME") or "").strip()
    matched = (os.environ.get("DUCKCLAW_PM2_MATCHED_APP_NAME") or "").strip()
    pretty = {
        "TheMind-Gateway": "The Mind",
        "Leila-Gateway": "Leila",
        "BI-Analyst-Gateway": "BI Analyst",
        "SIATA-Gateway": "SIATA Analyst",
        "Finanz-Gateway": "Finanz",
    }
    for key in (proc, matched):
        if key in pretty:
            return pretty[key]
    fallback = proc or matched
    if fallback:
        return fallback.replace("-Gateway", "").replace("-", " ").strip() or "este gateway"
    return "este gateway"


def _format_vault_size_mb(size_bytes: int | float) -> str:
    """Tamaño para mensajes /vault (1 MB = 1024² bytes, dos decimales)."""
    try:
        b = max(0, int(size_bytes))
    except (TypeError, ValueError):
        b = 0
    mb = b / (1024 * 1024)
    return f"{mb:.2f} MB"


def execute_vault(
    args: str,
    *,
    vault_user_id: Any,
    tenant_id: Any = None,
    db: Any | None = None,
) -> str:
    user_id = (str(vault_user_id or "").strip() or "default")
    vault_scope = vault_scope_id_for_tenant(tenant_id)
    raw = (args or "").strip()
    session_db_path = _session_duckdb_path_for_fly(db) if db is not None else None
    fixed_db = session_db_path or _dedicated_gateway_db_path_for_vault()
    if fixed_db:
        from pathlib import Path as _P

        fp = _P(fixed_db).expanduser().resolve()
        label = (
            _fly_vault_label_for_tenant(tenant_id)
            if session_db_path
            else _dedicated_gateway_vault_label()
        )
        if not raw:
            size = 0
            try:
                size = fp.stat().st_size if fp.exists() else 0
            except Exception:
                pass
            tid_req = str(tenant_id or "").strip()
            if tid_req and tid_req.lower() != "default":
                gtid = tid_req
            else:
                gtid = (os.environ.get("DUCKCLAW_GATEWAY_TENANT_ID") or "").strip()
            extra = f"\nTenant: {gtid}" if gtid else ""
            return (
                f"🗄 BD de este gateway ({label}): {fp.name}\n"
                f"Ruta: {fp}\nTamaño: {_format_vault_size_mb(size)}{extra}"
            )
        tokens = raw.split()
        cmd = (tokens[0] or "").strip().lower()
        if cmd.startswith("--"):
            cmd = cmd[2:]
        if cmd in ("list", "new", "use", "rm"):
            return (
                f"En este gateway ({label}) solo aplica la BD anterior. "
                "Los comandos /vault list|new|use|rm son del registry multi-bóveda en Finanz; "
                "aquí no aplican. Usa /vault sin argumentos para ver la ruta."
            )
        return (
            f"Usa /vault sin argumentos para ver la BD de {label}. "
            "Comandos adicionales del registry no aplican en este gateway."
        )
    if not raw:
        active_id, active_path = _vault_resolve_active(user_id, vault_scope)
        size = 0
        try:
            from pathlib import Path as _P
            p = _P(active_path)
            size = p.stat().st_size if p.exists() else 0
        except Exception:
            pass
        return (
            f"🗄 Bóveda activa: {active_id}\nRuta: {active_path}\nTamaño: {_format_vault_size_mb(size)}\n\n"
            "Comandos: /vault list | /vault --list | /vault new <name> | /vault --new <name> | "
            "/vault use <id> | /vault --use <id> | /vault rm <id> | /vault --rm <id>"
        
        )
    tokens = raw.split()
    cmd = (tokens[0] or "").strip().lower()
    # Compatibilidad: permitir flags estilo --list/--use/--new/--rm
    if cmd.startswith("--"):
        cmd = cmd[2:]
    if cmd == "list":
        rows = _vault_list(user_id, vault_scope)
        if not rows:
            return "No hay bóvedas."
        lines = []
        for r in rows:
            mark = "✅" if r.get("is_active") else "•"
            sz = int(r.get("size_bytes", 0) or 0)
            lines.append(
                f"{mark} {r.get('vault_id')} ({r.get('vault_name')}) - {_format_vault_size_mb(sz)}"
            )
        return "🗄 Bóvedas:\n" + "\n".join(lines)
    if cmd == "new":
        name = " ".join(tokens[1:]).strip()
        if not name:
            return "Uso: /vault new <name> | /vault --new <name>"
        created = _vault_create(user_id, name, vault_scope)
        return f"✅ Bóveda creada: {created.get('vault_id')} ({created.get('vault_name')})"
    if cmd == "use":
        vid = " ".join(tokens[1:]).strip()
        if not vid:
            return "Uso: /vault use <vault_id> | /vault --use <vault_id>"
        ok = _vault_switch(user_id, vid, vault_scope)
        if not ok:
            return f"No existe la bóveda '{vid}'. Usa /vault list."
        active_id, _ = _vault_resolve_active(user_id, vault_scope)
        return f"✅ Bóveda activa actual: {active_id}"
    if cmd == "rm":
        vid = " ".join(tokens[1:]).strip()
        if not vid:
            return "Uso: /vault rm <vault_id> | /vault --rm <vault_id>"
        ok = _vault_remove(user_id, vid, vault_scope)
        if not ok:
            return f"No existe la bóveda '{vid}'."
        active_id, _ = _vault_resolve_active(user_id, vault_scope)
        return f"🗑 Bóveda eliminada: {vid}. Activa actual: {active_id}"
    return (
        "Uso: /vault | /vault list | /vault --list | /vault new <name> | /vault --new <name> | "
        "/vault use <vault_id> | /vault --use <vault_id> | /vault rm <vault_id> | /vault --rm <vault_id>"
    


    )
def _team_whitelist_audit_enabled() -> bool:
    v = (os.environ.get("DUCKCLAW_TEAM_WHITELIST_DEBUG") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _audit_team_whitelist_rw(message: str, **data: Any) -> None:
    if not _team_whitelist_audit_enabled():
        return
    logging.getLogger("duckclaw.team_whitelist").info("%s %s", message, data)


def _paths_same_duckdb_file(a: str, b: str) -> bool:
    if not (a or "").strip() or not (b or "").strip():
        return False
    pa = Path(str(a).strip()).expanduser().resolve()
    pb = Path(str(b).strip()).expanduser().resolve()
    if str(pa) == str(pb):
        return True
    try:
        return bool(pa.samefile(pb))
    except OSError:
        return False


def _try_duckdb_checkpoint_rw(db: Any) -> None:
    if getattr(db, "_read_only", True):
        return
    try:
        db.execute("CHECKPOINT")
    except Exception:
        pass


def _team_whitelist_db(fly_db: Any) -> Any:
    """
    Whitelist ``main.authorized_users`` se lee de la misma DuckDB que el hub
    (``get_gateway_db_path()``), vía ``get_db()`` (conexión RO efímera).

    Excepción: en el API Gateway el bloque fly ya abrió ``fly_db`` en RW sobre ese
    archivo; abrir un segundo ``duckdb.connect(..., read_only=True)`` en paralelo
    puede lanzar ``ConnectionException``. En ese caso reutilizamos ``fly_db``.
    """
    try:
        from duckclaw.gateway_db import get_gateway_db_path  # noqa: PLC0415
        from duckclaw.graphs.graph_server import get_db as _gw_acl_db  # noqa: PLC0415

        gw = str(Path(get_gateway_db_path()).resolve())
        fp = ""
        try:
            fpraw = getattr(fly_db, "_path", "") or ""
            if fpraw and str(fpraw).strip() not in ("", ":memory:"):
                fp = str(Path(str(fpraw)).expanduser().resolve())
        except Exception:
            fp = ""
        same = _paths_same_duckdb_file(fp, gw) if fp else False
        fly_rw = getattr(fly_db, "_read_only", True) is False
        if same and fly_rw and hasattr(fly_db, "query"):
            return fly_db
        return _gw_acl_db()
    except Exception:
        return fly_db


def _authorized_users_rw_connection(fly_db: Any) -> tuple[Any, Callable[[], None]]:
    """
    ``graph_server.get_db()`` es RO efímero: ``execute`` no persiste. Las mutaciones
    de whitelist deben usar DuckClaw RW sobre ``get_gateway_db_path()`` o reutilizar
    ``fly_db`` si ya apunta al mismo archivo en modo RW (p. ej. bot Finanz).
    """
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import GatewayDbEphemeralReadonly, get_gateway_db_path

    acl_ro = _team_whitelist_db(fly_db)
    if not isinstance(acl_ro, GatewayDbEphemeralReadonly):
        _audit_team_whitelist_rw(
            "rw_connection",
            branch="direct_acl_not_ephemeral",
            acl_type=type(acl_ro).__name__,
        )

        def _noop() -> None:
            return None

        return acl_ro, _noop

    gw = str(Path(get_gateway_db_path()).resolve())
    fly_resolved = ""
    try:
        fp = getattr(fly_db, "_path", "") or ""
        if fp and str(fp).strip() not in ("", ":memory:"):
            fly_resolved = str(Path(str(fp)).expanduser().resolve())
    except Exception:
        fly_resolved = ""

    reuse_fly = _paths_same_duckdb_file(fly_resolved, gw) and getattr(fly_db, "_read_only", True) is False

    _audit_team_whitelist_rw(
        "rw_connection",
        branch="gateway_ephemeral_acl",
        reuse_fly=reuse_fly,
        gw_tail=gw[-64:] if gw else "",
        fly_tail=fly_resolved[-64:] if fly_resolved else "",
        fly_read_only=getattr(fly_db, "_read_only", None),
    )

    if reuse_fly:

        def _noop_fly() -> None:
            return None

        return fly_db, _noop_fly

    # Mismo motor que GatewayDbEphemeralReadonly (duckdb Python). Si usamos C++ nativo en RW,
    # /team --add puede persistir pero /team (lectura RO Python) no ve las filas.
    _audit_team_whitelist_rw("rw_connection", branch="duckclaw_gw_python_engine", gw_tail=gw[-64:] if gw else "")
    rw = DuckClaw(gw, read_only=False, engine="python")

    def _close_rw() -> None:
        try:
            rw.close()
        except Exception:
            pass

    return rw, _close_rw


def execute_team_whitelist(db: Any, tenant_id: Any, requester_id: Any, args: str) -> str:
    """
    Telegram Guard spec: /team lista y muta authorized_users por tenant.
    - /team                           -> lista autorizados (para tenant)
    - /team --add <user_id> [nombre] [admin] (admin u owner DUCKCLAW_ADMIN_CHAT_ID)
    - /team --rm <user_id>            (admin u owner)
    """
    acl = _team_whitelist_db(db)
    tid = str(tenant_id or "default").strip() or "default"
    rid = str(requester_id or "").strip()

    raw = (args or "").strip()
    if _is_wr_tenant(tid):
        _ensure_war_room_tables(acl)
        requester_clearance = _wr_member_clearance(acl, tenant_id=tid, user_id=rid)

        if not raw:
            rows_raw = acl.query(
                "SELECT user_id, username, clearance_level FROM war_room_core.wr_members "
                f"WHERE lower(tenant_id)=lower('{_sql_escape_literal(tid, 128)}') ORDER BY user_id"
            )
            rows = json.loads(rows_raw) if isinstance(rows_raw, str) else (rows_raw or [])
            if not rows:
                return f"No hay miembros WR para tenant '{tid}'."
            lines_wr: list[str] = []
            seen_wr: set[str] = set()
            for r in rows:
                if not isinstance(r, dict):
                    continue
                uid = str(r.get("user_id") or "").strip()
                if not uid or uid in seen_wr:
                    continue
                seen_wr.add(uid)
                uname = str(r.get("username") or "").strip()
                clr = str(r.get("clearance_level") or "").strip().lower() or "observer"
                label = _player_label(uname, uid, db=acl, tenant_id=tid)
                lines_wr.append(f"- {label} ({uid}) · clearance: {clr}")
            body_wr = "\n".join(lines_wr)
            return f"🛡 Miembros War Room (tenant '{tid}'):\n{body_wr}"

        if raw.startswith("--rm "):
            if not (_is_gateway_owner_user(rid) or requester_clearance == "admin"):
                return "❌ Acceso denegado: solo admin WR puede eliminar miembros."
            tokens = [t for t in raw[5:].strip().split() if t.strip()]
            if not tokens:
                return "Uso WR: /team --rm <user_id>"
            target_uid = tokens[0]
            acl.execute(
                "DELETE FROM war_room_core.wr_members "
                f"WHERE lower(tenant_id)=lower('{_sql_escape_literal(tid, 128)}') "
                f"AND user_id='{_sql_escape_literal(target_uid, 128)}'"
            )
            _invalidate_wr_clearance_redis_cache(tenant_id=tid, user_id=target_uid)
            _wr_append_audit(
                acl,
                tenant_id=tid,
                sender_id=rid or "system",
                target_agent="manager",
                event_type="REMOVE_WR_MEMBER",
                payload=f"user_id={target_uid}",
            )
            target_label = _player_label("", target_uid, db=acl, tenant_id=tid)
            return f"✅ Miembro WR eliminado: {target_label}."

        if raw.startswith("--add ") or raw.strip() == "--add":
            if not (_is_gateway_owner_user(rid) or requester_clearance == "admin"):
                return "❌ Acceso denegado: solo admin WR puede agregar miembros."
            ids_part = raw[6:].strip() if raw.startswith("--add ") else ""
            tokens = [t for t in ids_part.split() if t.strip()]
            if not tokens:
                return "Uso WR: /team --add <user_id> [username] [admin|operator|observer]"
            target_uid = tokens[0]
            clearance = "observer"
            if len(tokens) >= 2 and tokens[-1].lower() in ("admin", "operator", "observer"):
                clearance = tokens[-1].lower()
                tokens = tokens[:-1]
            username = " ".join(tokens[1:]).strip() if len(tokens) > 1 else "Usuario"
            acl.execute(
                "INSERT INTO war_room_core.wr_members (tenant_id, user_id, username, clearance_level) "
                f"VALUES ('{_sql_escape_literal(tid, 128)}', '{_sql_escape_literal(target_uid, 128)}', "
                f"'{_sql_escape_literal(username or 'Usuario', 128)}', '{_sql_escape_literal(clearance, 32)}') "
                "ON CONFLICT (tenant_id, user_id) DO UPDATE SET "
                "username=EXCLUDED.username, clearance_level=EXCLUDED.clearance_level, added_at=now()"
            )
            _invalidate_wr_clearance_redis_cache(tenant_id=tid, user_id=target_uid)
            _wr_append_audit(
                acl,
                tenant_id=tid,
                sender_id=rid or "system",
                target_agent="manager",
                event_type="REGISTER_WR_MEMBER",
                payload=f"user_id={target_uid} clearance={clearance}",
            )
            target_label = _player_label(username, target_uid, db=acl, tenant_id=tid)
            return f"✅ Miembro WR registrado: {target_label} ({clearance})."

        return (
            "Uso WR: /team | /team --add <user_id> [username] [admin|operator|observer] | /team --rm <user_id>"
        )

    if not raw:
        users = _dedupe_authorized_users_by_user_id(_list_authorized_users(acl, tenant_id=tid))
        if not users:
            hint = ""
            if _is_gateway_owner_user(rid):
                hint = (
                    " Como eres el owner del gateway (DUCKCLAW_OWNER_ID o DUCKCLAW_ADMIN_CHAT_ID), puedes ejecutar "
                    "`/team --add <user_id> [nombre] [admin]` para dar de alta."
                )
            return f"No hay usuarios autorizados para tenant '{tid}'.{hint}"
        body_lines: list[str] = []
        for u in users:
            uid = str(u.get("user_id") or "").strip()
            uname = str(u.get("username") or "").strip()
            role = (u.get("role") or "user").strip().lower() or "user"
            label = _player_label(uname, uid, db=acl, tenant_id=tid)
            body_lines.append(f"- {label} ({uid}) · rol: {role}")
        return f"🦆 Usuarios autorizados (tenant '{tid}'):\n" + "\n".join(body_lines)

    if raw.startswith("--rm "):
        if not rid:
            return "❌ Acceso denegado."
        if not _is_team_admin(acl, tenant_id=tid, requester_id=rid):
            return "❌ Acceso denegado: solo administradores pueden eliminar usuarios."
        target_uid = raw[5:].strip().split()[0]
        if not target_uid:
            return "Uso: /team --rm <user_id>"
        mut_db, mut_close = _authorized_users_rw_connection(db)
        try:
            _delete_authorized_user(mut_db, tenant_id=tid, user_id=target_uid)
            _try_duckdb_checkpoint_rw(mut_db)
        finally:
            mut_close()
        _invalidate_whitelist_redis_cache(tenant_id=tid, user_id=target_uid)
        target_label = _player_label("", target_uid, db=acl, tenant_id=tid)
        return f"✅ Eliminado {target_label} del tenant '{tid}'."

    if raw.startswith("--add ") or raw.strip() == "--add":
        if not rid:
            return "❌ Acceso denegado."
        if not _is_team_admin(acl, tenant_id=tid, requester_id=rid):
            return "❌ Acceso denegado: solo administradores pueden agregar usuarios."
        ids_part = raw[6:].strip() if raw.startswith("--add ") else ""
        tokens = [t for t in ids_part.split() if t.strip()]
        if not tokens:
            return "Uso: /team --add <user_id> [nombre] [admin]"
        role_out = "user"
        if len(tokens) >= 2 and tokens[-1].lower() == "admin":
            role_out = "admin"
            tokens = tokens[:-1]
        if not tokens:
            return "Uso: /team --add <user_id> [nombre] [admin]"
        target_uid = tokens[0]
        uname = tokens[1] if len(tokens) > 1 else "Usuario"
        mut_db, mut_close = _authorized_users_rw_connection(db)
        try:
            _upsert_authorized_user(mut_db, tenant_id=tid, user_id=target_uid, username=uname, role=role_out)
            _try_duckdb_checkpoint_rw(mut_db)
        finally:
            mut_close()
        _invalidate_whitelist_redis_cache(tenant_id=tid, user_id=target_uid)
        target_label = _player_label(uname, target_uid, db=acl, tenant_id=tid)
        return f"✅ Añadido {target_label} (role={role_out}) al tenant '{tid}'."

    if raw == "--shared-list" or raw.startswith("--shared-list"):
        if not rid:
            return "❌ Acceso denegado."
        if not _is_team_admin(acl, tenant_id=tid, requester_id=rid):
            return "❌ Acceso denegado: solo administradores pueden listar permisos de bases compartidas."
        from duckclaw.shared_db_grants import list_shared_grants_for_tenant

        grants = list_shared_grants_for_tenant(acl, tenant_id=tid)
        if not grants:
            return (
                f"🗂 No hay filas en user_shared_db_access para tenant '{tid}'. "
                "Sin filas, cualquier usuario whitelist puede usar rutas shared válidas (compat). "
                "Admin: /team --shared-grant <user_id> <resource_key> (ej. default o *)."
            )
        grant_lines: list[str] = []
        for g in grants:
            grant_lines.append(
                f"- user={g.get('user_id')} key={g.get('resource_key')} at={g.get('created_at')}"
            )
        return f"🗂 Bases compartidas permitidas (tenant '{tid}'):\n\n" + "\n".join(grant_lines)

    if raw.startswith("--shared-grant "):
        if not rid:
            return "❌ Acceso denegado."
        if not _is_team_admin(acl, tenant_id=tid, requester_id=rid):
            return "❌ Acceso denegado: solo administradores."
        rest = raw[len("--shared-grant ") :].strip().split(None, 1)
        if len(rest) < 2:
            return (
                "Uso: /team --shared-grant <user_id> <resource_key>\n"
                "resource_key: default, * (todas), o slug (env DUCKCLAW_SHARED_RESOURCE_<SLUG>)."
            )
        target_uid, rkey = rest[0], rest[1].strip()
        from duckclaw.shared_db_grants import upsert_shared_grant, validate_resource_key

        if not validate_resource_key(rkey):
            return "resource_key inválido (usa default, * o slug alfanumérico)."
        upsert_shared_grant(acl, tenant_id=tid, user_id=target_uid, resource_key=rkey)
        return f"✅ Grant shared '{rkey}' → user {target_uid} (tenant '{tid}')."

    if raw.startswith("--shared-revoke "):
        if not rid:
            return "❌ Acceso denegado."
        if not _is_team_admin(acl, tenant_id=tid, requester_id=rid):
            return "❌ Acceso denegado: solo administradores."
        rest = raw[len("--shared-revoke ") :].strip().split(None, 1)
        if len(rest) < 2:
            return "Uso: /team --shared-revoke <user_id> <resource_key>"
        target_uid, rkey = rest[0], rest[1].strip()
        from duckclaw.shared_db_grants import delete_shared_grant, validate_resource_key

        if not validate_resource_key(rkey):
            return "resource_key inválido."
        delete_shared_grant(acl, tenant_id=tid, user_id=target_uid, resource_key=rkey)
        return f"✅ Revocado shared '{rkey}' para user {target_uid}."

    return (
        "Uso: /team | /team --add ... | /team --rm ... | /team --shared-list | "
        "/team --shared-grant <user_id> <resource_key> | /team --shared-revoke <user_id> <resource_key>"
    )


def execute_roles(db: Any, chat_id: Any) -> str:
    """/roles: lista todos los trabajadores virtuales (templates) disponibles. El manager solo delegará a los que estén en /workers."""
    from duckclaw.workers.factory import list_workers
    all_templates = list_workers()
    if not all_templates:
        return "No hay templates en forge/templates. Añade al menos uno."
    lines = "\n".join(f"- {w}" for w in all_templates)
    return (
        "🦆 Trabajadores virtuales (templates) disponibles:\n\n"
        f"{lines}\n\n"
        "El manager solo delegará a los que estén en tu equipo. Para añadirlos: /workers id1 id2 ..."
    )


# Worker por defecto: el manager orquesta y delega a los trabajadores en forge/templates
_DEFAULT_WORKER = "manager"


def execute_role_switch(db: Any, chat_id: Any, worker_id: str) -> str:
    """/role <worker_id>: cambia el rol. Por defecto 'manager' delega a los templates. Sin args: muestra rol actual y disponibles."""
    from duckclaw.workers.factory import list_workers
    available = list_workers()  # solo templates (finanz, research_worker, etc.)
    wid_raw = (worker_id or "").strip()
    if not wid_raw:
        current = get_chat_state(db, chat_id, "worker_id") or _DEFAULT_WORKER
        if current == "manager":
            current_display = "Manager (delega a trabajadores en templates)"
        else:
            try:
                from duckclaw.workers.manifest import load_manifest
                spec = load_manifest(current)
                current_display = f"{spec.name} ({current})"
            except Exception:
                current_display = current
        avail_str = "\n".join(f"- {w}" for w in available) if available else "ninguna"
        return (
            f"🦆 Rol: {current_display}\n\n"
            f"Disponibles: manager (por defecto)\n{avail_str}\n/role <id>"
        )
    if wid_raw.lower() == "manager":
        set_chat_state(db, chat_id, "worker_id", "manager")
        return "✅ Manager. Delega a los trabajadores en templates."
    canonical = _resolve_template_id(available, wid_raw)
    if not canonical:
        avail_str = "\n".join(f"- {w}" for w in available) if available else "ninguna"
        return f"Rol '{wid_raw}' no existe.\nDisponibles:\n{avail_str}"
    try:
        from duckclaw.workers.manifest import load_manifest
        spec = load_manifest(canonical)
        set_chat_state(db, chat_id, "worker_id", canonical)
        skills = ", ".join(spec.skills_list or []) or "read_sql, admin_sql"
        return f"✅ {spec.name} ({canonical}). Herramientas: {skills}"
    except Exception as e:
        return f"Error al cargar rol: {e}."


def execute_skills_list(db: Any, chat_id: Any, args: str) -> str:
    """/skills <worker_id>: lista herramientas del template. worker_id debe ser uno de /roles."""
    from duckclaw.workers.factory import list_workers
    available = list_workers()
    wid_raw = (args or "").strip()
    if not wid_raw:
        return "Uso: /skills <worker_id>. Ver templates: /roles"
    if wid_raw.startswith("--"):
        return "Indica un worker_id (ej. finanz, research_worker). Ver templates: /roles"
    canonical = _resolve_template_id(available, wid_raw)
    if not canonical:
        return f"Template '{wid_raw}' no encontrado. Disponibles (usa /roles): {', '.join(available)}"
    try:
        from duckclaw.workers.manifest import load_manifest
        spec = load_manifest(canonical)
        skill_lines = [f"- {s}" for s in (spec.skills_list or [])]
        skill_lines.append("- read_sql (solo lectura)")
        skill_lines.append("- admin_sql (lectura + escrituras)")
        return f"🔧 {spec.name} ({canonical})\n" + "\n".join(skill_lines)
    except Exception as e:
        return f"Error: {e}."


def execute_forget(db: Any, chat_id: Any) -> str:
    """/forget: borra historial de la conversación y reinicia estado."""
    try:
        cid = int(chat_id)
        # Telegram: chat_id is numeric, use telegram_conversation
        db.execute(f"DELETE FROM telegram_conversation WHERE chat_id = {cid}")
    except (TypeError, ValueError):
        # API gateway: session_id is string (e.g. "default"), use api_conversation
        sid = str(chat_id).replace("'", "''")[:256]
        try:
            db.execute(f"DELETE FROM api_conversation WHERE session_id = '{sid}'")
        except Exception:
            pass  # Table may not exist if only Telegram used
    try:
        set_chat_state(db, chat_id, "last_audit", "")
    except Exception:
        pass
    if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true":
        try:
            import langsmith
            # Log evento Habeas Data (opcional: run_id no disponible aquí)
            pass
        except Exception:
            pass
    return "✅ Historial borrado."


def _ensure_the_mind_schema(db: Any) -> None:
    """DDL único para The Mind + migraciones ligeras."""
    if _skip_runtime_ddl(db):
        return
    db.execute(
        "CREATE TABLE IF NOT EXISTS the_mind_games ("
        "game_id VARCHAR PRIMARY KEY, "
        "status VARCHAR, "
        "current_level INTEGER, "
        "lives INTEGER, "
        "shurikens INTEGER, "
        "cards_played INTEGER[])"
    )
    try:
        import json as _json

        info = db.query("PRAGMA table_info('the_mind_games')")
        rows = _json.loads(info) if isinstance(info, str) else (info or [])
        col_names = {str(r.get("name")) for r in rows if isinstance(r, dict)}
        if "chat_id" in col_names and "game_id" not in col_names:
            db.execute("ALTER TABLE the_mind_games RENAME COLUMN chat_id TO game_id")
        if "level" in col_names and "current_level" not in col_names:
            db.execute("ALTER TABLE the_mind_games RENAME COLUMN level TO current_level")
        if "status" not in col_names:
            db.execute("ALTER TABLE the_mind_games ADD COLUMN status VARCHAR DEFAULT 'waiting'")
    except Exception:
        pass
    db.execute(
        "CREATE TABLE IF NOT EXISTS the_mind_players ("
        "game_id VARCHAR, "
        "chat_id VARCHAR, "
        "username VARCHAR, "
        "cards INTEGER[], "
        "is_ready BOOLEAN, "
        "PRIMARY KEY (game_id, chat_id))"
    )
    try:
        db.execute("ALTER TABLE the_mind_players ADD COLUMN user_id VARCHAR")
    except Exception:
        pass
    db.execute(
        "CREATE TABLE IF NOT EXISTS the_mind_moves ("
        "game_id VARCHAR, "
        "chat_id VARCHAR, "
        "username VARCHAR, "
        "move_type VARCHAR, "
        "card_value INTEGER, "
        "level INTEGER, "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )


def _merge_the_mind_player(
    db: Any,
    game_id: str,
    chat_id: str,
    username: str,
    *,
    user_id: str | None = None,
) -> None:
    """Inserta o actualiza jugador en partida (preserva mano si ya existía)."""
    uid = (user_id or "").strip() or None
    ex = list(
        db.execute(
            "SELECT 1 FROM the_mind_players WHERE game_id = ? AND chat_id = ?",
            (game_id, chat_id),
        )
    )
    if ex:
        if uid:
            db.execute(
                "UPDATE the_mind_players SET username = ?, user_id = COALESCE(?, user_id) "
                "WHERE game_id = ? AND chat_id = ?",
                (username or "", uid, game_id, chat_id),
            )
        else:
            db.execute(
                "UPDATE the_mind_players SET username = ? WHERE game_id = ? AND chat_id = ?",
                (username or "", game_id, chat_id),
            )
    else:
        db.execute(
            "INSERT INTO the_mind_players (game_id, chat_id, username, cards, is_ready, user_id) "
            "VALUES (?, ?, ?, ARRAY[]::INTEGER[], FALSE, ?)",
            (game_id, chat_id, username or "", uid),
        )


def _mind_tx_begin(db: Any) -> None:
    try:
        db.execute("BEGIN TRANSACTION")
    except Exception:
        try:
            db.execute("BEGIN")
        except Exception:
            pass


def _mind_tx_commit(db: Any) -> None:
    try:
        db.execute("COMMIT")
    except Exception:
        pass


def _mind_tx_rollback(db: Any) -> None:
    try:
        db.execute("ROLLBACK")
    except Exception:
        pass


def _insert_mind_move(
    db: Any,
    *,
    game_id: str,
    chat_id: str,
    username: str,
    move_type: str,
    card_value: int | None = None,
    level: int | None = None,
) -> None:
    try:
        db.execute(
            """
            INSERT INTO the_mind_moves (game_id, chat_id, username, move_type, card_value, level)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                game_id,
                chat_id,
                username or "",
                move_type,
                int(card_value) if card_value is not None else None,
                int(level) if level is not None else None,
            ),
        )
    except Exception:
        pass


def _team_username_by_user_id(db: Any, tenant_id: str | None, user_id: Any) -> str:
    tid = str(tenant_id or "default").strip() or "default"
    uid = str(user_id or "").strip()
    if not uid:
        return ""
    for u in _list_authorized_users(db, tenant_id=tid):
        if str(u.get("user_id") or "").strip() == uid:
            return str(u.get("username") or "").strip()
    return ""


def _player_label(username: Any, chat_id: Any, *, db: Any | None = None, tenant_id: str | None = None) -> str:
    uname = str(username or "").strip()
    cid = str(chat_id or "").strip() or "unknown"
    if not uname and db is not None:
        uname = _team_username_by_user_id(db, tenant_id, chat_id)
    if uname:
        if cid.isdigit():
            return f"[@{uname}](tg://user?id={cid})"
        return f"@{uname}"
    if cid.isdigit():
        return f"[{cid}](tg://user?id={cid})"
    return cid


def _player_label_log(username: Any, chat_id: Any, *, db: Any | None = None, tenant_id: str | None = None) -> str:
    """Formato para logs PM2: @alias (user_id)."""
    uname = str(username or "").strip()
    if not uname and db is not None:
        uname = _team_username_by_user_id(db, tenant_id, chat_id)
    cid = str(chat_id or "").strip() or "unknown"
    return f"@{uname} ({cid})" if uname else cid


def _chat_log_identity_for_context(
    chat_id: Any,
    *,
    db: Any | None = None,
    tenant_id: str | None = None,
) -> str:
    """Etiqueta para cabecera de logs PM2: @alias (user_id) con fallback a user_id."""
    cid = str(chat_id if chat_id is not None else "unknown").strip() or "unknown"
    uname = ""
    if db is not None:
        try:
            uname = str(get_chat_state(db, chat_id, "username") or "").strip()
        except Exception:
            uname = ""
        if not uname:
            uname = _team_username_by_user_id(db, tenant_id, chat_id)
    return f"@{uname} ({cid})" if uname else cid


def _notify_level_up_with_private_hands(
    db: Any,
    game_id: str,
    completed_level: int,
    next_level: int,
    *,
    exclude_chat_id: str | None = None,
) -> None:
    """Envía DM individual a cada jugador al subir nivel con su nueva mano (solo sus cartas)."""
    try:
        rows = list(
            db.execute(
                "SELECT chat_id, username, cards FROM the_mind_players WHERE game_id = ?",
                (game_id,),
            )
        )
        exclude = (exclude_chat_id or "").strip()
        for pchat, puname, cards in rows:
            cid = str(pchat or "").strip()
            if exclude and cid == exclude:
                continue
            hand = sorted(int(c) for c in list(cards or []))
            send_telegram_dm(
                cid,
                f"🃏 Tus nuevas cartas: {hand}",
                username=str(puname or ""),
                db=db,
                tenant_id="default",
            )
    except Exception:
        pass


_THE_MIND_MAX_LEVEL = 12


def _team_allows_user(db: Any, tenant_id: str | None, user_id: Any) -> tuple[bool, str]:
    """
    Si hay al menos un usuario en authorized_users del tenant, solo esos user_id
    pueden crear/unirse a partidas The Mind. Si la lista está vacía, no se restringe
    (compatibilidad con despliegues sin whitelist).
    """
    tid = str(tenant_id or "default").strip() or "default"
    users = _list_authorized_users(db, tenant_id=tid)
    if not users:
        return True, ""
    uid = str(user_id or "").strip()
    if not uid:
        return False, "Falta identidad de usuario (user_id). El Gateway debe enviar user_id para The Mind."
    allowed = {str(u.get("user_id") or "").strip() for u in users if u.get("user_id")}
    if uid in allowed:
        return True, ""
    return (
        False,
        "Solo pueden jugar usuarios listados en /team para este tenant. Pide a un admin que ejecute `/team --add <tu_user_id>`.",
    )


def _all_mind_players_in_team(db: Any, game_id: str, tenant_id: str | None) -> tuple[bool, str]:
    """
    Si /team no está vacío, todos los jugadores deben tener user_id y estar en la whitelist.
    Si /team está vacío, no se exige user_id (compatibilidad con clientes sin identidad).
    """
    tid = str(tenant_id or "default").strip() or "default"
    roster = _list_authorized_users(db, tenant_id=tid)
    if not roster:
        return True, ""
    allowed = {str(u.get("user_id") or "").strip() for u in roster if u.get("user_id")}
    rows = list(db.execute("SELECT user_id FROM the_mind_players WHERE game_id = ?", (game_id,)))
    for (uid_raw,) in rows:
        uid = str(uid_raw or "").strip()
        if not uid:
            return (
                False,
                "No se puede iniciar: falta user_id en algún jugador. Con /team configurado, cada uno debe usar `/join` desde un cliente que envíe user_id al Gateway.",
            )
        if uid not in allowed:
            return (
                False,
                f"No se puede iniciar: {_player_label('', uid, db=db, tenant_id=tid)} no está en /team para este tenant.",
            )
    return True, ""


def _the_mind_invite_hint(db: Any, tenant_id: str | None, game_id: str) -> str:
    """Texto corto: equipo /team, DMs vs avisos, pasos para invitar e iniciar."""
    tid = str(tenant_id or "default").strip() or "default"
    users = _list_authorized_users(db, tenant_id=tid)
    if users:
        team_lines = []
        for u in users:
            uid = str(u.get("user_id") or "").strip()
            uname = str(u.get("username") or "").strip()
            label = f"@{uname}" if uname else uid
            team_lines.append(f"- {label}")
        team_block = "\n".join(team_lines)
    else:
        team_block = "(Nadie en /team: un admin debe usar /team --add <user_id> [nombre].)"

    return (
        "\n\n---\n"
        "Cómo invitar e iniciar:\n"
        "• Solo pueden unirse quienes estén en /team (tenant actual).\n"
        "• Las cartas solo se envían a los chat_id registrados en la partida: cada jugador debe /join desde su DM con el bot (no basta con un grupo).\n"
        "• Requiere webhook de salida en el gateway (p. ej. DUCKCLAW_TELEGRAM_SEND_WEBHOOK_URL); si falta, verás aviso al iniciar.\n"
        "• Cartas: cada jugador recibe un mensaje distinto por DM.\n"
        "• Avisos del juego (nivel, errores, victoria): el mismo texto a todos los DM de la partida.\n"
        f"• Equipo autorizado ahora:\n{team_block}\n"
        f"• Pasos: cada jugador abre DM con el bot y envía /join {game_id}.\n"
        f"• Luego el anfitrión: /start_mind {game_id} (mínimo 2 jugadores; ver /game).\n"
    


    )
def _new_game_id() -> str:
    """Genera un identificador de partida único (game_id)."""
    # timestamp en segundos + sufijo aleatorio corto
    import time
    import random
    import string

    ts = int(time.time())
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"game_{ts}_{suffix}"


def execute_new_game(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
) -> str:
    """/new_game the_mind: crea una nueva partida de The Mind y devuelve el game_id."""
    game_type = (args or "").strip().lower()
    if game_type not in ("the_mind", "themind", "themindcrupier"):
        return "Uso: /new_game the_mind"
    try:
        _ensure_the_mind_schema(db)
        tid = str(tenant_id or "default").strip() or "default"
        ok, err = _team_allows_user(db, tid, requester_id)
        if not ok:
            return err
        game_id = _new_game_id()
        db.execute(
            "INSERT INTO the_mind_games (game_id, status, current_level, lives, shurikens, cards_played) "
            "VALUES (?, 'waiting', 1, 3, 1, ARRAY[]::INTEGER[])",
            (game_id,),
        )
        cid = str(chat_id).replace("'", "''")[:256]
        uname = get_chat_state(db, chat_id, "username") or ""
        rid = str(requester_id or "").strip() or None
        _merge_the_mind_player(db, game_id, cid, uname, user_id=rid)
        base = (
            f"🧠 The Mind: partida creada con id {game_id}. "
            f"Cada jugador debe enviar `/join {game_id}` desde el chat privado (DM) con el bot para quedar registrado y recibir cartas."
        )
        return base + _the_mind_invite_hint(db, tid, game_id)
    except Exception as e:
        return f"No se pudo crear la partida de The Mind: {e}"


def execute_join_game(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
) -> str:
    """/join <game_id>: añade al jugador (este chat) a la partida indicada."""
    game_id = (args or "").strip()
    if not game_id:
        return "Uso: /join <game_id>. Ejemplo: /join game_1234"
    try:
        _ensure_the_mind_schema(db)
        tid = str(tenant_id or "default").strip() or "default"
        ok, err = _team_allows_user(db, tid, requester_id)
        if not ok:
            return err
        rows = list(
            db.execute(
                "SELECT game_id, status FROM the_mind_games WHERE game_id = ?", (game_id,)
            )
        )
        if not rows:
            return f"No existe ninguna partida con id {game_id}."
        status = str(rows[0][1] or "").strip().lower()
        if status not in ("waiting", "playing"):
            return (
                f"La partida {game_id} no acepta más jugadores (estado actual: {status or 'desconocido'})."
            
            )
        cid = str(chat_id).replace("'", "''")[:256]
        uname = get_chat_state(db, chat_id, "username") or ""
        rid = str(requester_id or "").strip() or None
        _merge_the_mind_player(db, game_id, cid, uname, user_id=rid)
        # Avisar por DM al/los admin del tenant cuando alguien se une.
        try:
            n_rows = list(
                db.execute("SELECT COUNT(*) FROM the_mind_players WHERE game_id = ?", (game_id,))
            )
            n_players = int(n_rows[0][0]) if n_rows else 0
            actor = _player_label(uname, (rid or chat_id), db=db, tenant_id=tid)
            admin_users = [
                u for u in _list_authorized_users(db, tenant_id=tid)
                if (u.get("role") or "").strip().lower() == "admin"
            ]
            notice = (
                f"🧠 {actor} se unió a la partida {game_id}. "
                f"Jugadores: {n_players}. Usa /start_mind {game_id} cuando estén todos."
            )
            sent_to: set[str] = set()
            for u in admin_users:
                admin_uid = str(u.get("user_id") or "").strip()
                if not admin_uid or admin_uid in sent_to:
                    continue
                send_telegram_dm(
                    admin_uid,
                    notice,
                    username=str(u.get("username") or ""),
                    db=db,
                    tenant_id=tid,
                )
                sent_to.add(admin_uid)
        except Exception:
            # Best-effort: no bloquear el join por problemas de notificación.
            pass
        return (
            f"✅ Te has unido a la partida {game_id}. Espera a que el anfitrión inicie con `/start_mind {game_id}`."
        
        )
    except Exception as e:
        return f"No se pudo unir a la partida: {e}"


def execute_list_mind_games(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
) -> str:
    """/game: listar partidas activas; /game --end cierra tu partida activa; admin: /game --rm <game_id>|all cancela partidas activas."""
    raw = (args or "").strip()
    tid = str(tenant_id or "default").strip() or "default"
    rid = str(requester_id or "").strip()

    # End current player's active game (self-service)
    if raw == "--end":
        cid = str(chat_id).replace("'", "''")[:256]
        try:
            _ensure_the_mind_schema(db)
            rows = list(
                db.execute(
                    """
                    SELECT g.game_id
                    FROM the_mind_games g
                    JOIN the_mind_players p ON p.game_id = g.game_id
                    WHERE p.chat_id = ? AND lower(COALESCE(g.status, '')) IN ('waiting', 'playing')
                    ORDER BY g.rowid DESC
                    LIMIT 1
                    """,
                    (cid,),
                )
            )
            if not rows:
                return "No estás en ninguna partida activa."
            game_id = str(rows[0][0] or "").strip()
            if not game_id:
                return "No estás en ninguna partida activa."
            db.execute(
                "UPDATE the_mind_games SET status = 'cancelled' WHERE game_id = ?",
                (game_id,),
            )
            try:
                broadcast_message_to_players(
                    db,
                    game_id,
                    f"🛑 Partida finalizada: {game_id}",
                    exclude_chat_id=cid,
                )
            except Exception:
                pass
            return f"🛑 Partida finalizada: {game_id}"
        except Exception as e:
            return f"No se pudo finalizar la partida: {e}"

    # Admin-only cancel flow
    if raw.startswith("--rm "):
        role = _get_authorized_role(db, tenant_id=tid, user_id=rid) if rid else ""
        if role != "admin":
            return "Solo el admin puede cancelar partidas."

        target = raw[5:].strip().split()[0] if raw[5:].strip() else ""
        if not target:
            return "Uso: /game --rm <game_id> | /game --rm all"
        try:
            _ensure_the_mind_schema(db)
            if target.lower() == "all":
                rows = list(
                    db.execute(
                        """
                        SELECT game_id
                        FROM the_mind_games
                        WHERE lower(COALESCE(status, '')) IN ('waiting', 'playing')
                        ORDER BY game_id DESC
                        """
                    )
                )
                game_ids = [str(r[0]) for r in rows if r and r[0]]
                if not game_ids:
                    return "No hay partidas activas que cancelar."
                db.execute(
                    """
                    UPDATE the_mind_games
                    SET status = 'cancelled'
                    WHERE lower(COALESCE(status, '')) IN ('waiting', 'playing')
                    """
                )
                return f"🗑️ Partida(s) cancelada(s): [{', '.join(game_ids)}]"

            rows = list(
                db.execute(
                    """
                    SELECT game_id
                    FROM the_mind_games
                    WHERE game_id = ? AND lower(COALESCE(status, '')) IN ('waiting', 'playing')
                    LIMIT 1
                    """,
                    (target,),
                )
            )
            if not rows:
                return "No hay partidas activas que cancelar."
            game_id = str(rows[0][0])
            db.execute(
                "UPDATE the_mind_games SET status = 'cancelled' WHERE game_id = ?",
                (game_id,),
            )
            return f"🗑️ Partida(s) cancelada(s): [{game_id}]"
        except Exception as e:
            return f"No se pudo cancelar partidas: {e}"
    try:
        _ensure_the_mind_schema(db)
        rows = list(
            db.execute(
                """
                SELECT g.game_id, g.status, g.current_level, g.lives,
                       COUNT(p.chat_id) AS n
                FROM the_mind_games g
                LEFT JOIN the_mind_players p ON p.game_id = g.game_id
                WHERE lower(COALESCE(g.status, '')) IN ('waiting', 'playing')
                GROUP BY g.game_id, g.status, g.current_level, g.lives
                ORDER BY g.game_id DESC
                """
            )
        )
    except Exception as e:
        return f"No se pudo listar partidas: {e}"
    if not rows:
        return (
            "No hay partidas activas (waiting/playing). Usa /new_mind para crear una."
        
        )
    # Durante partida: para un jugador en estado playing devolver estado resumido (sin revelar manos).
    try:
        cid = str(chat_id).replace("'", "''")[:256]
        current = list(
            db.execute(
                """
                SELECT g.game_id, g.current_level, g.lives, g.shurikens, g.cards_played
                FROM the_mind_games g
                JOIN the_mind_players p ON p.game_id = g.game_id
                WHERE g.status = 'playing' AND p.chat_id = ?
                ORDER BY g.rowid DESC
                LIMIT 1
                """,
                (cid,),
            )
        )
        if current:
            game_id, lvl, lives, stars, cards_played = current[0]
            total_remaining_rows = list(
                db.execute(
                    "SELECT cards FROM the_mind_players WHERE game_id = ?",
                    (game_id,),
                )
            )
            remaining = sum(len(list(r[0] or [])) for r in total_remaining_rows)
            cards_table = list(cards_played or [])
            return (
                f"🧠 Nivel: {int(lvl or 1)} | Vidas: {int(lives or 0)} | Estrellas: {int(stars or 0)}\n"
                f"Cartas en mesa: {cards_table} | Cartas restantes: {remaining}"
            
            )
    except Exception:
        pass

    lines: list[str] = []
    for r in rows:
        gid, st, lvl, lives, n = r[0], r[1], r[2], r[3], r[4]
        players_rows = list(
            db.execute(
                "SELECT chat_id, username FROM the_mind_players WHERE game_id = ? ORDER BY chat_id",
                (gid,),
            )
        )
        # Importante: evitar Markdown links `[...] (tg://...)` aquí, porque algunos nodos Telegram
        # (n8n) usan parse_mode Markdown/MarkdownV2 y pueden fallar con entidades TextUrl anidadas.
        players_labels = [
            _player_label_log(uname, pchat, db=db, tenant_id=tid)
            for pchat, uname in players_rows
        ]
        players_text = ", ".join(players_labels) if players_labels else "sin jugadores"
        lines.append(
            f"• {gid} — estado={st or '?'} | jugadores={int(n or 0)} | "
            f"nivel={int(lvl or 1)} | vidas={int(lives or 0)} | "
            f"participantes={players_text}"
        )
    body = "\n".join(lines)
    return f"🧠 Partidas activas:\n{body}"


def execute_start_game(db: Any, chat_id: Any, args: str) -> str:
    """/start_game [game_id]: cambia el estado de la partida a 'playing' para comenzar el nivel 1."""
    game_id = (args or "").strip()
    try:
        if not game_id:
            # Inferir: última partida 'waiting' creada
            rows = list(
                db.execute(
                    "SELECT game_id FROM the_mind_games WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1"
                )
            )
            if not rows:
                return (
                    "No encontré ninguna partida en estado 'waiting'. Usa `/new_mind` o `/new_game the_mind`."
                
                )
            game_id = str(rows[0][0])
        rows = list(
            db.execute(
                "SELECT status FROM the_mind_games WHERE game_id = ?", (game_id,)
            )
        )
        if not rows:
            return f"No existe ninguna partida con id {game_id}."
        status = str(rows[0][0] or "").strip().lower()
        if status == "playing":
            return f"La partida {game_id} ya está en juego."
        if status not in ("waiting",):
            return (
                f"No se puede iniciar la partida {game_id} desde el estado {status or 'desconocido'}."
            
            )
        db.execute(
            "UPDATE the_mind_games SET status = 'playing', current_level = COALESCE(current_level, 1) "
            "WHERE game_id = ?",
            (game_id,),
        )
        return (
            f"🧠 The Mind: partida {game_id} en estado playing. Reparte cartas con `/start_mind {game_id}` o `/deal`."
        
        )
    except Exception as e:
        return f"No se pudo iniciar la partida: {e}"


def execute_start_mind(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
) -> str:
    """
    /start_mind [game_id]: pasa la partida a playing, reparte el Nivel 1 por DM
    y anuncia por broadcast.
    """
    try:
        _ensure_the_mind_schema(db)
        tid = str(tenant_id or "default").strip() or "default"
        starter_id = str(requester_id or "").strip() or str(chat_id or "").strip()
        starter_role = _get_authorized_role(db, tenant_id=tid, user_id=starter_id)
        if starter_role != "admin":
            return "Solo el admin puede iniciar la partida."
        ok_host, err_host = _team_allows_user(db, tid, requester_id)
        if not ok_host:
            return err_host
        game_id = (args or "").strip()
        cid = str(chat_id).replace("'", "''")[:256]

        if not game_id:
            rows = list(
                db.execute(
                    """
                    SELECT g.game_id
                    FROM the_mind_games g
                    JOIN the_mind_players p ON p.game_id = g.game_id
                    WHERE g.status = 'waiting' AND p.chat_id = ?
                    ORDER BY g.rowid DESC
                    LIMIT 1
                    """,
                    (cid,),
                )
            )
            if not rows:
                rows = list(
                    db.execute(
                        "SELECT game_id FROM the_mind_games WHERE status = 'waiting' "
                        "ORDER BY rowid DESC LIMIT 1"
                    )
                )
            if not rows:
                return (
                    "No encontré ninguna partida en espera. Usa `/new_mind` o `/new_game the_mind`."
                
                )
            game_id = str(rows[0][0])

        rows = list(
            db.execute(
                "SELECT status FROM the_mind_games WHERE game_id = ?", (game_id,)
            )
        )
        if not rows:
            return f"No existe ninguna partida con id {game_id}."
        status = str(rows[0][0] or "").strip().lower()
        if status != "waiting":
            return (
                f"La partida {game_id} no está en espera (estado: {status or 'desconocido'}). "
                "Solo se puede `/start_mind` desde 'waiting'."
            

            )
        n_players = list(
            db.execute(
                "SELECT COUNT(*) FROM the_mind_players WHERE game_id = ?", (game_id,)
            )
        )
        count = int(n_players[0][0]) if n_players else 0
        if count < 1:
            return "No hay jugadores en esta partida."

        allow_solo = (os.environ.get("DUCKCLAW_THE_MIND_ALLOW_SOLO") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if count < 2 and not allow_solo:
            return (
                f"Solo hay {count} jugador(es) en la partida {game_id}. "
                "Se necesitan al menos 2: cada uno debe enviar `/join "
                f"{game_id}` por DM con el bot. Usa /game para ver el estado. "
                "(Modo 1 jugador: define DUCKCLAW_THE_MIND_ALLOW_SOLO=true en el gateway.)"
            

            )
        ok_roster, err_roster = _all_mind_players_in_team(db, game_id, tid)
        if not ok_roster:
            return err_roster

        db.execute(
            "UPDATE the_mind_games SET status = 'playing', current_level = 1, "
            "cards_played = ARRAY[]::INTEGER[] WHERE game_id = ?",
            (game_id,),
        )
        # Orden requerido de mensajes al iniciar:
        # 1) anuncio global de comienzo, 2) DM "Nivel 1 ...", 3) DM con cartas.
        broad_res = broadcast_message_to_players(
            db,
            game_id,
            "🎮 ¡La partida ha comenzado! Recuerden: sin comunicación. "
            "Jueguen en orden ascendente. Vidas: 3 | Estrellas: 1",
        )
        try:
            players = list(
                db.execute(
                    "SELECT chat_id, username FROM the_mind_players WHERE game_id = ?",
                    (game_id,),
                )
            )
            for pchat, puname in players:
                send_telegram_dm(
                    str(pchat or ""),
                    (
                        "🧠 Nivel 1 — tienes 1 carta(s). Cuando quieras jugar una, "
                        "escribe /play <número>. No le digas tu carta a nadie."
                    ),
                    username=str(puname or ""),
                    db=db,
                    tenant_id=tid,
                )
        except Exception:
            pass
        deal_res = deal_cards_for_level(db, game_id, 1)
        return (
            f"🧠 Partida {game_id} iniciada (Nivel 1 en BD).\n"
            f"• {broad_res.summary_line}\n"
            f"• {deal_res.summary_line}"
        
        )
    except Exception as e:
        return f"No se pudo iniciar The Mind: {e}"


def execute_deal(db: Any, chat_id: Any, args: str) -> str:
    """/deal [game_id]: reparte cartas según current_level de la partida en juego."""
    try:
        _ensure_the_mind_schema(db)
        game_id = (args or "").strip()
        cid = str(chat_id).replace("'", "''")[:256]
        if not game_id:
            rows = list(
                db.execute(
                    """
                    SELECT g.game_id, g.current_level
                    FROM the_mind_games g
                    JOIN the_mind_players p ON p.game_id = g.game_id
                    WHERE g.status = 'playing' AND p.chat_id = ?
                    ORDER BY g.rowid DESC
                    LIMIT 1
                    """,
                    (cid,),
                )
            )
            if not rows:
                return (
                    "No hay partida en juego para este chat. Usa `/join` y `/start_mind` primero."
                
                )
            game_id = str(rows[0][0])
            lvl = int(rows[0][1] or 1)
        else:
            lr = list(
                db.execute(
                    "SELECT current_level FROM the_mind_games WHERE game_id = ? AND status = 'playing'",
                    (game_id,),
                )
            )
            if not lr:
                return f"No hay partida en juego con id {game_id}."
            lvl = int(lr[0][0] or 1)
        deal_res = deal_cards_for_level(db, game_id, lvl)
        return f"🃏 {deal_res.summary_line}"
    except Exception as e:
        return f"No se pudo repartir: {e}"


def execute_play_mind(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: Any = None,
) -> str:
    """/play <numero>: juega una carta en The Mind usando the_mind_games/the_mind_players."""
    num_str = (args or "").strip()
    if not num_str:
        return "Uso: /play <numero>. Ejemplo: /play 15"
    try:
        num = int(num_str)
    except Exception:
        return "La carta debe ser un número entero. Ejemplo: /play 15"
    if num <= 0 or num > 100:
        return "La carta debe estar entre 1 y 100."

    cid = str(chat_id).replace("'", "''")[:256]
    uname = get_chat_state(db, chat_id, "username") or ""
    tid = str(tenant_id or "default").strip() or "default"
    uname_display = _player_label(uname, cid, db=db, tenant_id=tid)

    try:
        _ensure_the_mind_schema(db)
        _mind_tx_begin(db)
        rows = list(
            db.execute(
                """
                SELECT g.game_id, g.cards_played, g.current_level, g.status
                FROM the_mind_games g
                JOIN the_mind_players p ON g.game_id = p.game_id
                WHERE g.status = 'playing' AND p.chat_id = ?
                ORDER BY g.rowid DESC
                LIMIT 1
                """,
                (cid,),
            )
        )
        if not rows:
            _mind_tx_rollback(db)
            return (
                "No encontré ninguna partida en juego asociada a este chat. "
                "Usa `/join` y `/start_mind`."
            
            )
        game_id, cards_played_arr, current_level, _st = rows[0]
        cards_played = list(cards_played_arr or [])
        _insert_mind_move(
            db,
            game_id=str(game_id),
            chat_id=cid,
            username=uname or "",
            move_type="play_attempt",
            card_value=num,
            level=int(current_level or 1),
        )

        prow = list(
            db.execute(
                "SELECT cards FROM the_mind_players WHERE game_id = ? AND chat_id = ?",
                (game_id, cid),
            )
        )
        if not prow:
            _mind_tx_rollback(db)
            return (
                "No encontré tu mano en esta partida. Espera a que se repartan cartas con `/start_mind`."
            
            )
        hand = list(prow[0][0] or [])
        if num not in hand:
            _mind_tx_rollback(db)
            return (
                f"No tienes la carta {num} en tu mano actual. Verifica tus cartas privadas."
            

            )
        lower_exists = False
        offender_name = ""
        offender_chat = ""
        offender_username = ""
        offender_card: int | None = None
        all_rows_for_validation = list(
            db.execute(
                "SELECT chat_id, username, cards FROM the_mind_players WHERE game_id = ?",
                (game_id,),
            )
        )
        for pchat, puname, pcards in all_rows_for_validation:
            if pcards:
                for c in pcards:
                    if int(c) < num:
                        lower_exists = True
                        if offender_card is None or int(c) < offender_card:
                            offender_card = int(c)
                            offender_chat = str(pchat or "")
                            offender_username = str(puname or "")
                            offender_name = _player_label(puname, pchat, db=db, tenant_id=tid)
                        break
            if lower_exists and offender_card is not None and offender_card == 1:
                # No puede existir carta menor que 1; corte rápido.
                break

        if lower_exists:
            life_row = list(
                db.execute(
                    "SELECT lives FROM the_mind_games WHERE game_id = ?", (game_id,)
                )
            )
            lives = int(life_row[0][0] or 0) if life_row else 0
            new_lives = max(lives - 1, 0)

            all_hands = list(
                db.execute(
                    "SELECT chat_id, username, cards FROM the_mind_players WHERE game_id = ?",
                    (game_id,),
                )
            )
            discarded_notes: list[str] = []
            discarded_count = 0
            for pch, puname, pcards in all_hands:
                raw = list(pcards or [])
                # En penalización, descartar solo la carta en conflicto detectada
                # (offender_card) y no todas las menores a `num`.
                discarded_cards: list[int] = []
                new_hand: list[int] = []
                removed_conflict = False
                for c in raw:
                    ci = int(c)
                    if (
                        offender_card is not None
                        and not removed_conflict
                        and ci == int(offender_card)
                    ):
                        discarded_cards.append(ci)
                        removed_conflict = True
                        continue
                    new_hand.append(ci)
                # En penalización, la carta jugada también sale de la mano del actor.
                if str(pch or "") == cid:
                    removed_played = False
                    actor_hand: list[int] = []
                    for c in new_hand:
                        if not removed_played and int(c) == int(num):
                            removed_played = True
                            continue
                        actor_hand.append(int(c))
                    new_hand = actor_hand
                db.execute(
                    "UPDATE the_mind_players SET cards = ? WHERE game_id = ? AND chat_id = ?",
                    (new_hand, game_id, pch),
                )
                owner = _player_label(puname, pch, db=db, tenant_id=tid)
                for dc in discarded_cards:
                    _insert_mind_move(
                        db,
                        game_id=str(game_id),
                        chat_id=str(pch or ""),
                        username=str(puname or ""),
                        move_type="discarded",
                        card_value=int(dc),
                        level=int(current_level or 1),
                    )
                    discarded_notes.append(f"{owner} tenía el {dc} (descartado)")
                    discarded_count += 1
            db.execute(
                "UPDATE the_mind_games SET lives = ? WHERE game_id = ?",
                (new_lives, game_id),
            )
            _insert_mind_move(
                db,
                game_id=str(game_id),
                chat_id=cid,
                username=uname or "",
                move_type="play_error_life_lost",
                card_value=num,
                level=int(current_level or 1),
            )
            if new_lives <= 0:
                db.execute("UPDATE the_mind_games SET status = 'lost' WHERE game_id = ?", (game_id,))

            hands_after_penalty = list(
                db.execute("SELECT cards FROM the_mind_players WHERE game_id = ?", (game_id,))
            )
            level_done_after_penalty = all(len(list(h[0] or [])) == 0 for h in hands_after_penalty)
            lvl_now = int(current_level or 1)
            _mind_tx_commit(db)
            try:
                _obs = get_obs_logger("duckclaw.fly")
                log_fly(
                    _obs,
                    "/play penalty -> game_id=%s actor=%s offender=%s discarded=%s lives=%s",
                    str(game_id),
                    _player_label_log(uname, cid, db=db, tenant_id=tid),
                    _player_label_log(offender_username, offender_chat, db=db, tenant_id=tid),
                    discarded_count,
                    new_lives,
                )
            except Exception:
                pass
            try:
                _ = discarded_notes
                broadcast_message_to_players(
                    db,
                    game_id,
                    f"💀 {uname_display} jugó el {num} pero {offender_name or 'unknown'} tenía el {offender_card or '?'} (descartado). "
                    f"Vidas restantes: {new_lives}",
                    exclude_chat_id=cid,
                )
                if new_lives <= 0:
                    broadcast_message_to_players(
                        db,
                        game_id,
                        f"💀 Game over. Llegaron al Nivel {int(current_level or 1)}. ¡Buen intento!",
                        exclude_chat_id=cid,
                    )
            except Exception:
                pass
            if new_lives <= 0:
                return (
                    f"💀 {uname_display} jugó el {num} pero {offender_name or 'unknown'} tenía el {offender_card or '?'} (descartado). "
                    f"Vidas restantes: {new_lives}\n"
                    f"💀 Game over. Llegaron al Nivel {int(current_level or 1)}. ¡Buen intento!"
                
                )
            if level_done_after_penalty:
                # Regla operativa: una penalización nunca avanza de nivel.
                # Si tras el descarte no quedan cartas, se reinicia el mismo nivel.
                next_lvl = lvl_now
                db.execute(
                    "UPDATE the_mind_games SET cards_played = ARRAY[]::INTEGER[] WHERE game_id = ?",
                    (game_id,),
                )
                try:
                    broadcast_message_to_players(
                        db,
                        game_id,
                        f"⚠️ Penalización en Nivel {lvl_now}. Reiniciando Nivel {next_lvl}...",
                        exclude_chat_id=cid,
                    )
                    deal_cards_for_level(db, game_id, next_lvl, exclude_chat_id=cid)
                except Exception:
                    pass
                try:
                    sender_rows = list(
                        db.execute(
                            "SELECT cards FROM the_mind_players WHERE game_id = ? AND chat_id = ? LIMIT 1",
                            (game_id, cid),
                        )
                    )
                    sender_hand = sorted(int(c) for c in list((sender_rows[0][0] if sender_rows else []) or []))
                except Exception:
                    sender_hand = []
                return (
                    f"💀 {uname_display} jugó el {num} pero {offender_name or 'unknown'} tenía el {offender_card or '?'} (descartado). "
                    f"Vidas restantes: {new_lives}\n"
                    f"⚠️ Penalización en Nivel {lvl_now}. Reiniciando Nivel {next_lvl}...\n"
                    + f"🃏 Tus nuevas cartas: {sender_hand}"
                
                )
            return (
                f"❌ ¡ERROR! {uname_display} jugó el {num}, pero {offender_name or 'unknown'} tenía una carta menor. "
                f"Pierden 1 vida. Vidas restantes: {new_lives}."
            

            )
        hand.remove(num)
        db.execute(
            "UPDATE the_mind_players SET cards = ? WHERE game_id = ? AND chat_id = ?",
            (hand, game_id, cid),
        )
        cards_played.append(num)
        cards_played_sorted = sorted(cards_played)
        db.execute(
            "UPDATE the_mind_games SET cards_played = ? WHERE game_id = ?",
            (cards_played_sorted, game_id),
        )
        _insert_mind_move(
            db,
            game_id=str(game_id),
            chat_id=cid,
            username=uname or "",
            move_type="play_ok",
            card_value=num,
            level=int(current_level or 1),
        )

        lvl_now = int(current_level or 1)
        hands_after = list(
            db.execute("SELECT cards FROM the_mind_players WHERE game_id = ?", (game_id,))
        )
        level_done = all(len(list(h[0] or [])) == 0 for h in hands_after)
        cards_remaining = sum(len(list(h[0] or [])) for h in hands_after)

        _mind_tx_commit(db)

        msg = (
            f"✅ {uname_display} jugó el {num}. Cartas jugadas en este nivel: {cards_played_sorted}."
        )
        try:
            broadcast_message_to_players(
                db,
                game_id,
                f"✅ {uname_display} jugó el {num}. "
                f"Mesa: {cards_played_sorted} | Cartas restantes: {cards_remaining}",
                exclude_chat_id=cid,
            )
        except Exception:
            pass

        if level_done:
            if lvl_now >= _THE_MIND_MAX_LEVEL:
                db.execute(
                    "UPDATE the_mind_games SET status = 'won' WHERE game_id = ?",
                    (game_id,),
                )
                broadcast_message_to_players(
                    db,
                    game_id,
                    f"🏆 ¡Victoria! Han completado los {_THE_MIND_MAX_LEVEL} niveles.",
                )
                msg += " 🏆 ¡Victoria final!"
            else:
                next_lvl = lvl_now + 1
                db.execute(
                    "UPDATE the_mind_games SET cards_played = ARRAY[]::INTEGER[] WHERE game_id = ?",
                    (game_id,),
                )
                broadcast_message_to_players(
                    db,
                    game_id,
                    f"🎉 ¡Nivel {lvl_now} superado! Subiendo al Nivel {next_lvl}...",
                    exclude_chat_id=cid,
                )
                deal_cards_for_level(db, game_id, next_lvl, exclude_chat_id=cid)
                try:
                    sender_rows = list(
                        db.execute(
                            "SELECT cards FROM the_mind_players WHERE game_id = ? AND chat_id = ? LIMIT 1",
                            (game_id, cid),
                        )
                    )
                    sender_hand = sorted(int(c) for c in list((sender_rows[0][0] if sender_rows else []) or []))
                except Exception:
                    sender_hand = []
                msg += (
                    f" 🎉 ¡Nivel {lvl_now} completado! Repartido el Nivel {next_lvl}.\n"
                    f"🃏 Tus nuevas cartas: {sender_hand}"
                )
            return msg

        return msg
    except Exception as e:
        try:
            _mind_tx_rollback(db)
        except Exception:
            pass
        return f"No se pudo registrar la jugada: {e}"


def execute_cards(db: Any, chat_id: Any, args: str) -> str:
    """/cards: muestra las cartas activas del jugador en su partida en curso."""
    _ = args
    try:
        _ensure_the_mind_schema(db)
        cid = str(chat_id).replace("'", "''")[:256]
        rows = list(
            db.execute(
                """
                SELECT p.cards
                FROM the_mind_players p
                JOIN the_mind_games g ON g.game_id = p.game_id
                WHERE p.chat_id = ? AND g.status = 'playing'
                ORDER BY g.rowid DESC
                LIMIT 1
                """,
                (cid,),
            )
        )
        if not rows:
            return "No estás en ninguna partida en curso."
        cards = list(rows[0][0] or [])
        if not cards:
            return "No te quedan cartas en este nivel."
        cards_sorted = sorted(int(c) for c in cards)
        return f"🃏 Tus cartas: {', '.join(str(c) for c in cards_sorted)}"
    except Exception as e:
        return f"No se pudo consultar tus cartas: {e}"

def execute_context_toggle(db: Any, chat_id: Any, on_off: str) -> str:
    """/context on|off: activa o desactiva inyección de memoria a largo plazo."""
    v = (on_off or "").strip().lower()
    if v in ("on", "1", "true", "sí", "si"):
        set_chat_state(db, chat_id, "use_rag", "true")
        return "✅ Contexto largo activado (más mensajes en historial)."
    if v in ("off", "0", "false"):
        set_chat_state(db, chat_id, "use_rag", "false")
        return "✅ Contexto largo desactivado (solo historial reciente)."
    current = get_chat_state(db, chat_id, "use_rag")
    return (
        "Uso: `/context on` | `/context off` | `/context --add <texto>` | `/context --summary` (`--summarize`)\n"
        f"Estado actual (historial largo): {'on' if current != 'false' else 'off'}."
    )


def execute_sandbox_toggle(db: Any, chat_id: Any, on_off: str) -> str:
    """/sandbox on|off: habilita/deshabilita ejecución de código para este chat (por `agent_config`)."""
    v = (on_off or "").strip().lower()

    def _parse(v_: str) -> Optional[bool]:
        vv = (v_ or "").strip().lower()
        if vv in ("on", "1", "true", "sí", "si"):
            return True
        if vv in ("off", "0", "false"):
            return False
        return None

    parsed = _parse(v)
    if parsed is True:
        set_chat_state(db, chat_id, "sandbox_enabled", "true")
        db_path = getattr(db, "_path", None) or getattr(db, "path", None) or "(unknown_db_path)"
        # Warning para asegurar que aparezca en logs de pm2.
        import logging
        logging.getLogger(__name__).warning(
            "[sandbox-toggle] db_path=%r chat_id=%r sandbox_enabled=%r",
            db_path,
            chat_id,
            "true",
        )
        return "Entendido. He habilitado mis capacidades de ejecución de código para esta sesión."
    if parsed is False:
        set_chat_state(db, chat_id, "sandbox_enabled", "false")
        db_path = getattr(db, "_path", None) or getattr(db, "path", None) or "(unknown_db_path)"
        import logging
        logging.getLogger(__name__).warning(
            "[sandbox-toggle] db_path=%r chat_id=%r sandbox_enabled=%r",
            db_path,
            chat_id,
            "false",
        )
        return "Entendido. He desactivado mis capacidades de ejecución de código para esta sesión."

    # Sin args válidos: mostrar estado actual.
    current = _parse(get_chat_state(db, chat_id, "sandbox_enabled"))
    status = "habilitado" if current is True else "desactivado"  # default OFF
    return f"Uso: /sandbox on|off\nEstado actual: {status}."


def execute_heartbeat(db: Any, chat_id: Any, on_off: str, *, tenant_id: Any = None) -> str:
    """/heartbeat on|off — DM proactivos (Bot API nativa o webhook) mientras el agente usa herramientas."""
    from duckclaw.graphs.chat_heartbeat import (
        heartbeat_outbound_configured,
        heartbeat_redis_configured,
        is_chat_heartbeat_enabled,
        set_chat_heartbeat_enabled,
    )

    tid = str(tenant_id or "default").strip() or "default"
    cid = str(chat_id if chat_id is not None else "unknown").strip() or "unknown"
    v = (on_off or "").strip().lower()

    if not heartbeat_redis_configured():
        return (
            "Heartbeat requiere Redis (REDIS_URL o DUCKCLAW_REDIS_URL). Sin eso no se puede guardar el estado."
        

        )
    if v in ("on", "1", "true", "sí", "si"):
        if is_chat_heartbeat_enabled(tid, cid):
            return "✅ Heartbeat ya estaba activado."
        ok, err = set_chat_heartbeat_enabled(tid, cid, True)
        if not ok:
            return f"No se pudo activar heartbeat: {err}"
        if not heartbeat_outbound_configured():
            return (
                "Heartbeat activado en Redis, pero falta TELEGRAM_BOT_TOKEN (recomendado) o un webhook "
                "(DUCKCLAW_HEARTBEAT_WEBHOOK_URL / N8N_OUTBOUND_WEBHOOK_URL); no se enviarán DMs."
            
            )
        return (
            "✅ Heartbeat activado. Te avisaré por DM mientras uso herramientas."
        
        )
    if v in ("off", "0", "false"):
        if not is_chat_heartbeat_enabled(tid, cid):
            return "Heartbeat ya estaba desactivado."
        ok, err = set_chat_heartbeat_enabled(tid, cid, False)
        if not ok:
            return f"No se pudo desactivar heartbeat: {err}"
        return "✅ Heartbeat desactivado."

    st = "on" if is_chat_heartbeat_enabled(tid, cid) else "off"
    return f"Heartbeat: {st}\nUso: /heartbeat on | /heartbeat off"


def execute_audit(db: Any, chat_id: Any) -> str:
    """/audit: evidencia de la última ejecución (SQL, latencia, run_id)."""
    raw = get_chat_state(db, chat_id, "last_audit")
    if not raw:
        return "No hay evidencia de última ejecución. Envía un mensaje y vuelve a usar /audit."
    try:
        data = json.loads(raw)
        sql = data.get("sql") or "(no registrado)"
        latency_ms = data.get("latency_ms") or "—"
        tokens = data.get("tokens") or "—"
        run_id = data.get("run_id") or "—"
        return (
            f"📋 Última ejecución\nSQL: {str(sql)[:300]}\nLatencia: {latency_ms} ms\nTokens: {tokens}\nLangSmith run_id: {run_id}"
        
        )
    except Exception:
        return "Datos de auditoría no válidos."


def execute_health(db: Any) -> str:
    """/health: estado de infraestructura (MLX, DuckDB, latencia)."""
    lines = []
    # DuckDB
    try:
        db.query("SELECT 1")
        lines.append("✅ DuckDB: conectado")
    except Exception as e:
        lines.append(f"❌ DuckDB: {e}")
    # MLX / inference
    base_url = os.environ.get("DUCKCLAW_LLM_BASE_URL", "").strip() or "http://127.0.0.1:8080"
    if base_url:
        base = base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        url = base + "/health"
        try:
            import urllib.request
            t0 = time.perf_counter()
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                elapsed = int((time.perf_counter() - t0) * 1000)
                lines.append(f"✅ Inferencia ({url[:40]}...): {elapsed} ms")
        except Exception as e:
            lines.append(f"⚠️ Inferencia: {e}")
    return "\n".join(lines) or "Sin comprobaciones."


def execute_approve_reject(db: Any, chat_id: Any, approved: bool) -> str:
    """/approve o /reject: HITL (grafo en interrupt). Sin interrupt implementado: mensaje informativo."""
    return "No hay operación pendiente de aprobación. (El grafo no está en estado interrupt en esta versión.)"


def _normalize_belief_key(key: str) -> str:
    """Normaliza key para DB: alfanumérico y guión bajo."""
    return "".join(c if c.isalnum() or c == "_" else "_" for c in (key or "").strip())


def _get_goals_registry_for_manager() -> Optional[Any]:
    """Registro de goals válidos para el manager (desde el primer template con homeostasis, ej. finanz)."""
    try:
        from duckclaw.workers.factory import list_workers
        from duckclaw.workers.manifest import load_manifest
        from duckclaw.forge.homeostasis.belief_registry import BeliefRegistry
        for wid in list_workers():
            try:
                spec = load_manifest(wid)
                config = getattr(spec, "homeostasis_config", None) or {}
                registry = BeliefRegistry.from_config(config)
                if registry.beliefs:
                    return registry
            except Exception:
                continue
    except Exception:
        pass
    return None


def get_manager_goals(db: Any, chat_id: Any) -> list:
    """Goals del chat guardados por el manager. Por defecto vacío."""
    raw = get_chat_state(db, chat_id, "goals")
    if not raw:
        return []
    try:
        out = json.loads(raw)
        return out if isinstance(out, list) else []
    except Exception:
        return []


def set_manager_goals(db: Any, chat_id: Any, goals: list) -> None:
    """Guarda la lista de goals del chat (manager). Cada item: belief_key, target_value, threshold, observed_value opcional, title (resumen)."""
    set_chat_state(db, chat_id, "goals", json.dumps(goals))


def _goal_title(goal: dict, fallback_key: str) -> str:
    """Título resumen del goal para listar en /goals."""
    t = (goal.get("title") or "").strip()
    if t:
        return t[:80] + ("…" if len((goal.get("title") or "").strip()) > 80 else "")
    return (goal.get("belief_key") or fallback_key or "").strip()


def _natural_language_goal_to_params(db: Any, chat_id: Any, text: str) -> Optional[dict]:
    """Convierte un objetivo en lenguaje natural a parámetros homeostasis (belief_key, target_value, threshold, title). Usa LLM del manager."""
    text = (text or "").strip()[:500]
    if not text:
        return None
    try:
        from langchain_core.messages import HumanMessage
        provider, model, base_url = _effective_llm_triplet_for_chat_ui(db, chat_id)
        from duckclaw.integrations.llm_providers import build_llm
        llm = build_llm(provider, model, base_url, prefer_env_provider=False)
        if llm is None:
            return None
        prompt = (
            "Convierte este objetivo en lenguaje natural a parámetros para homeostasis (Active Inference). "
            "Responde ÚNICAMENTE un JSON válido con estas claves: belief_key (slug en snake_case, inglés o español), "
            "target_value (número; 0 si el objetivo es minimizar o cualitativo), threshold (número >= 0, tolerancia), "
            "title (resumen corto en español, máx 60 caracteres). Sin explicación, solo el JSON.\n\nObjetivo: "
        ) + text
        resp = llm.invoke([HumanMessage(content=prompt)])
        content = (getattr(resp, "content", None) or "").strip()
        if not content:
            return None
        # Extraer JSON si viene envuelto en ```json ... ```
        if "```" in content:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                content = content[start:end]
        data = json.loads(content)
        if not isinstance(data, dict):
            return None
        key = (data.get("belief_key") or "").strip() or _normalize_belief_key(text)
        key = _normalize_belief_key(key) or "objetivo"
        target = float(data.get("target_value", 0))
        thresh = max(0.0, float(data.get("threshold", 0)))
        title = (data.get("title") or text)[:120].strip()
        return {"belief_key": key, "target_value": target, "threshold": thresh, "title": title}
    except Exception:
        return None


def execute_goals(db: Any, chat_id: Any, args: str) -> str:
    """/goals [--reset] | /goals <goal>: listar, resetear o añadir. Acepta clave (presupuesto_mensual) o lenguaje natural; el manager convierte a parámetros homeostasis."""
    from duckclaw.forge.homeostasis.surprise import compute_surprise
    registry = _get_goals_registry_for_manager()
    valid_keys = [b.key for b in (registry.beliefs if registry else [])]
    goals = get_manager_goals(db, chat_id)

    raw = (args or "").strip()
    do_reset = raw.lower() == "--reset"

    if do_reset:
        set_manager_goals(db, chat_id, [])
        return "✅ Objetivos reiniciados. Crea con /goals <objetivo en lenguaje natural o clave>."

    # Añadir: /goals <clave o lenguaje natural>
    if raw and not raw.startswith("--"):
        key_norm = _normalize_belief_key(raw)
        belief = None
        if registry:
            belief = registry.get_belief(raw.strip())
            if not belief:
                for b in registry.beliefs:
                    if _normalize_belief_key(b.key) == key_norm:
                        belief = b
                        break
        if belief:
            new_goal = {
                "belief_key": belief.key,
                "target_value": belief.target,
                "threshold": belief.threshold,
                "observed_value": None,
                "title": belief.key,
            }
        else:
            # Lenguaje natural: manager convierte a parámetros homeostasis vía LLM
            params = _natural_language_goal_to_params(db, chat_id, raw)
            if params:
                new_goal = {
                    "belief_key": params["belief_key"],
                    "target_value": params["target_value"],
                    "threshold": params["threshold"],
                    "observed_value": None,
                    "title": params["title"],
                }
            else:
                new_goal = {
                    "belief_key": key_norm or "objetivo",
                    "target_value": 0.0,
                    "threshold": 0.0,
                    "observed_value": None,
                    "title": raw[:120].strip(),
                }
        existing = [g for g in goals if (g.get("belief_key") or "").strip() == new_goal["belief_key"]]
        if existing:
            goals = [g for g in goals if (g.get("belief_key") or "").strip() != new_goal["belief_key"]]
        goals.append(new_goal)
        set_manager_goals(db, chat_id, goals)
        title_display = new_goal.get("title") or new_goal["belief_key"]
        return f"✅ Objetivo añadido: {title_display}"

    # Listar (por defecto vacío)
    if not goals:
        return "🎯 Manager\nNo hay goals. Crea con /goals <objetivo>, ej. /goals disminuir gasto en recreación."

    lines = ["🎯 Manager"]
    try:
        key_to_belief = {b.key.strip(): b for b in (registry.beliefs if registry else [])}
        for g in goals:
            key = (g.get("belief_key") or "").strip()
            b = key_to_belief.get(key)
            target = float(g.get("target_value")) if g.get("target_value") is not None else None
            thresh = float(g.get("threshold")) if g.get("threshold") is not None else None
            if b is not None:
                target = target if target is not None else b.target
                thresh = thresh if thresh is not None else b.threshold
            try:
                observed = float(g.get("observed_value")) if g.get("observed_value") is not None else None
            except (TypeError, ValueError):
                observed = None
            title = _goal_title(g, key)
            if observed is not None and target is not None and thresh is not None and (target != 0 or thresh != 0):
                res = compute_surprise(observed, target, thresh)
                st = "⚠️" if res.is_anomaly else "✓"
                lines.append(f"- {title}: target={target} (obs: {observed}) {st}")
            elif target is not None and thresh is not None:
                lines.append(f"- {title}: target={target}, thresh={thresh} (sin dato)")
            else:
                lines.append(f"- {title}")
    except Exception as e:
        return f"Error: {e}."
    return "\n".join(lines) + "\n\n/goals --reset"


def execute_tasks(db: Any, chat_id: Any) -> str:
    """/tasks: estado del ActivityManager (Redis): IDLE, BUSY, subagente, tarea actual, tiempo en ejecución."""
    from duckclaw.graphs.activity import get_activity
    data = get_activity(chat_id)
    if data is None:
        return "⏸ IDLE (Redis no configurado)."
    status = data.get("status", "IDLE")
    task = data.get("task", "")
    worker_id = data.get("worker_id", "") or ""
    started_at = data.get("started_at", 0)
    elapsed_s = ""
    if started_at and status == "BUSY":
        try:
            elapsed_s = f" · {int(time.time()) - int(started_at)}s"
        except Exception:
            pass
    # Guión en worker_id (p. ej. SIATA-Analyst) obliga a \- en MarkdownV2; muchos clientes muestran el \ literal.
    # Mismo criterio que label de gateway: espacio en lugar de guion para etiqueta legible sin escapes.
    worker_display = (worker_id or "").replace("-", " ").strip()
    worker_s = f" · {worker_display}" if worker_display else ""
    # Segunda línea: solo el título del plan (task), precedido por un bullet grande
    task_preview = f"• {str(task)[:60]}" if task else "—"
    icon = "▶" if status == "BUSY" else "⏸"
    return f"{icon} {status}{elapsed_s}{worker_s}\n" + task_preview


def _get_global_config(db: Any, key: str) -> str:
    """Read a global config key from agent_config (e.g. system_prompt)."""
    _ensure_agent_config(db)
    k = str(key).replace("'", "''")[:128]
    try:
        r = db.query(f"SELECT value FROM {_AGENT_CONFIG_TABLE} WHERE key = '{k}' LIMIT 1")
        rows = json.loads(r) if isinstance(r, str) else (r or [])
        if rows and isinstance(rows[0], dict):
            return (rows[0].get("value") or "").strip()
    except Exception:
        pass
    return ""


def _set_global_config(db: Any, key: str, value: str) -> None:
    """Write a global config key to agent_config."""
    _ensure_agent_config(db)
    k = str(key).replace("'", "''")[:128]
    v = str(value).replace("'", "''")[:16384]
    db.execute(
        f"""
        INSERT INTO {_AGENT_CONFIG_TABLE} (key, value) VALUES ('{k}', '{v}')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """
    )


def get_effective_system_prompt(db: Any, worker_id: Optional[str] = None) -> str:
    """
    Devuelve el system prompt efectivo para un worker:
    - Si worker_id está definido: 1) override system_prompt_<worker_id>, 2) soul.md + system_prompt.md del template (ver load_system_prompt). No usa global.
    - Si worker_id vacío: global system_prompt o "".
    """
    wid = (worker_id or "").strip()
    if wid:
        override = _get_global_config(db, f"system_prompt_{wid}")
        if override:
            return override
        try:
            from duckclaw.workers.manifest import load_manifest
            from duckclaw.workers.loader import load_system_prompt
            spec = load_manifest(wid)
            return (load_system_prompt(spec) or "").strip()
        except Exception:
            pass
        return ""
    current = _get_global_config(db, "system_prompt")
    return current if current else ""


_PROVIDERS = ("mlx", "ollama", "openai", "anthropic", "deepseek", "groq")

# Modelo por defecto al cambiar provider (evita "Model Not Exist" al pasar de MLX a cloud)
_DEFAULT_MODEL_BY_PROVIDER = {
    "deepseek": "deepseek-chat",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "groq": "llama-3.3-70b-versatile",
    "mlx": "",  # usa MLX_MODEL_ID o /v1/models
    "ollama": "llama3.2",
}

# Base URL por defecto al cambiar provider (evita mezclar host global PM2 con otro proveedor).
_DEFAULT_BASE_URL_BY_PROVIDER = {
    "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openai": "",
    "anthropic": "",
    "mlx": "",
    "ollama": "http://127.0.0.1:11434",
}


def _effective_llm_triplet_for_chat_ui(db: Any, chat_id: Any) -> tuple[str, str, str]:
    """provider/model/base_url efectivos (chat > global agent_config > env), con MLX forzado a host local."""
    from duckclaw.integrations.llm_providers import (
        _ensure_duckclaw_llm_env_from_legacy_llm_vars,
        mlx_openai_compatible_base_url,
    )

    _ensure_duckclaw_llm_env_from_legacy_llm_vars()
    p = (
        get_chat_state(db, chat_id, "llm_provider")
        or _get_global_config(db, "llm_provider")
        or os.environ.get("DUCKCLAW_LLM_PROVIDER", "mlx")
    ).strip().lower()
    m = (
        get_chat_state(db, chat_id, "llm_model")
        or _get_global_config(db, "llm_model")
        or os.environ.get("DUCKCLAW_LLM_MODEL", "")
    ).strip()
    u = (
        get_chat_state(db, chat_id, "llm_base_url")
        or _get_global_config(db, "llm_base_url")
        or os.environ.get("DUCKCLAW_LLM_BASE_URL", "")
    ).strip()
    if p == "mlx":
        ul = u.lower()
        if (not u) or "groq.com" in ul or "deepseek.com" in ul:
            u = mlx_openai_compatible_base_url()
        if not m:
            m = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
    return (p, m, u)


def chat_has_llm_chat_state_override(db: Any, chat_id: Any) -> bool:
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    for key in ("llm_provider", "llm_model", "llm_base_url"):
        if (get_chat_state(db, cid, key) or "").strip():
            return True
    return False


def resolve_llm_triplet_for_chat_invocation(db: Any, chat_id: Any) -> tuple[str, str, str] | None:
    """Si el chat tiene llm_* en agent_config, devuelve tripleta para build_llm; si no, None (usar cache env del gateway)."""
    if not chat_has_llm_chat_state_override(db, chat_id):
        return None
    return _effective_llm_triplet_for_chat_ui(db, chat_id)


def execute_model(db: Any, chat_id: Any, args: str) -> str:
    """/model [provider=mlx] [model=...] [base_url=...]: cambia proveedor/modelo LLM en caliente. Sin args muestra el actual."""
    if not args or not args.strip():
        provider, model, base_url = _effective_llm_triplet_for_chat_ui(db, chat_id)
        provider = provider or "—"
        model = model or "—"
        u_show = base_url or "—"
        base_url = u_show[:50] + "…" if len(u_show) > 50 else u_show
        return f"Modelo actual:\n- provider: {provider}\n- model: {model}\n- base_url: {base_url}\n\nUso: /model provider=mlx | /model provider=deepseek | /model model=Slayer-8B"
    for part in args.split("|"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k == "provider":
                if v and v.lower() not in _PROVIDERS:
                    return f"Provider desconocido: {v}. Válidos: {', '.join(_PROVIDERS)}"
                set_chat_state(db, chat_id, "llm_provider", v)
                # Al cambiar provider, resetear model al default para evitar "Model Not Exist"
                # (ej. Slayer-8B-v1.1 no existe en DeepSeak)
                if v.lower() == "mlx":
                    from duckclaw.integrations.llm_providers import mlx_openai_compatible_base_url

                    set_chat_state(db, chat_id, "llm_base_url", mlx_openai_compatible_base_url())
                    mid = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
                    set_chat_state(db, chat_id, "llm_model", mid)
                else:
                    default_model = _DEFAULT_MODEL_BY_PROVIDER.get(v.lower(), "")
                    set_chat_state(db, chat_id, "llm_model", default_model)
                    default_url = _DEFAULT_BASE_URL_BY_PROVIDER.get(v.lower(), "")
                    if default_url:
                        set_chat_state(db, chat_id, "llm_base_url", default_url)
                    else:
                        set_chat_state(db, chat_id, "llm_base_url", "")
            elif k == "model":
                set_chat_state(db, chat_id, "llm_model", v)
            elif k == "base_url":
                set_chat_state(db, chat_id, "llm_base_url", v)
    return "✅ Modelo actualizado. Los próximos mensajes usarán esta config."


def execute_prompt(db: Any, chat_id: Any, args: str) -> str:
    """/prompt <worker_id> [--change <nuevo prompt>]: ver o cambiar el system prompt del template. worker_id debe ser uno de /roles."""
    from duckclaw.workers.factory import list_workers
    all_templates = list_workers()
    raw = (args or "").strip()
    if not raw:
        return "Uso: /prompt <worker_id> [--change <texto>]. Ver templates: /roles"
    if raw.startswith("--"):
        return "Indica un worker_id (ej. finanz, research_worker). Ver templates: /roles"
    change_marker = " --change "
    idx = raw.lower().find(change_marker)
    if idx >= 0:
        worker_id = raw[:idx].strip().lower()
        new_prompt = raw[idx + len(change_marker):].strip()
    else:
        worker_id = raw.split()[0].strip().lower() if raw.split() else ""
        new_prompt = ""
    if not worker_id:
        return "Uso: /prompt <worker_id> [--change <texto>]. Ver templates: /roles"
    if worker_id not in all_templates:
        return f"Template '{worker_id}' no encontrado. Disponibles (usa /roles): {', '.join(all_templates)}"
    if new_prompt:
        _set_global_config(db, f"system_prompt_{worker_id}", new_prompt)
        preview = new_prompt[:200] + "..." if len(new_prompt) > 200 else new_prompt
        return f"✅ System prompt de {worker_id} actualizado.\nVista previa: {preview}"
    current = get_effective_system_prompt(db, worker_id)
    if not current:
        return f"System prompt de {worker_id}: (vacío o por defecto del template).\nPara cambiar: /prompt {worker_id} --change <texto>"
    preview = current[:400] + "..." if len(current) > 400 else current
    return f"System prompt de {worker_id}:\n{preview}\n\nPara cambiar: /prompt {worker_id} --change <texto>"


def _leila_fly_commands_enabled() -> bool:
    """Comandos /catalogo, /pedido, /ayuda del MVP Leila (spec: Asistente de Leila — MVP Telegram)."""
    if (os.environ.get("DUCKCLAW_LEILA_FLY_COMMANDS") or "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return (os.environ.get("DUCKCLAW_PM2_PROCESS_NAME") or "").strip() == "Leila-Gateway"


def _leila_shared_catalog_path() -> str:
    return (os.environ.get("DUCKCLAW_SHARED_DB_PATH") or "").strip()


def prepare_leila_fly_duckdb(
    db: Any,
    vault_path: str,
    *,
    user_id: Any,
    tenant_id: Any,
    acl_db: Any | None = None,
) -> None:
    """
    Si el catálogo vive en DUCKCLAW_SHARED_DB_PATH, ATTACH como `shared` sobre la conexión
    ya abierta a la bóveda del usuario (misma convención que build_worker_graph).
    acl_db: DuckDB del gateway (tabla user_shared_db_access); None omite ACL de grants (tests).
    """
    if not _leila_fly_commands_enabled():
        return
    shared = _leila_shared_catalog_path()
    if not shared:
        return
    uid = (str(user_id or "").strip() or "default")
    tid = (str(tenant_id or "").strip() or None)
    if not validate_user_db_path(uid, shared, tenant_id=tid):
        _obs = get_obs_logger()
        try:
            log_fly(_obs, "Leila fly: ruta shared rechazada por validate_user_db_path (user_id=%s)", uid)
        except Exception:
            pass
        return
    if acl_db is not None:
        from duckclaw.shared_db_grants import user_may_access_shared_path

        tid_grant = str(tenant_id or "default").strip() or "default"
        if not user_may_access_shared_path(
            acl_db, tenant_id=tid_grant, user_id=uid, shared_db_path=shared
        ):
            _obs = get_obs_logger()
            try:
                log_fly(_obs, "Leila fly: sin grant user_shared_db_access (user_id=%s tenant=%s)", uid, tid_grant)
            except Exception:
                pass
            return
    from duckclaw.workers.factory import _apply_forge_attaches

    _apply_forge_attaches(db, (vault_path or "").strip(), shared)
    setattr(db, "_leila_shared_catalog_attached", True)


def _leila_products_rel(db: Any) -> str:
    """Tabla calificada tras prepare_leila_fly_duckdb (ATTACH `shared`)."""
    if getattr(db, "_leila_shared_catalog_attached", False):
        return "shared.main.leila_products"
    return "main.leila_products"


def _leila_orders_rel(db: Any) -> str:
    if getattr(db, "_leila_shared_catalog_attached", False):
        return "shared.main.leila_orders"
    return "main.leila_orders"


def execute_leila_catalogo(db: Any, chat_id: Any) -> str:
    """/catalogo — productos activos (shared.main o main según DUCKCLAW_SHARED_DB_PATH)."""
    _ = chat_id
    rel = _leila_products_rel(db)
    try:
        raw = db.query(
            f"SELECT id, nombre, descripcion, tallas, precio, foto_url "
            f"FROM {rel} WHERE activo = true ORDER BY nombre"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception as e:
        return f"No pude leer el catálogo: {e}"
    if not rows:
        return "Catálogo vacío por ahora. Vuelve pronto."
    lines: list[str] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        tid = str(r.get("id") or "").strip()
        nom = str(r.get("nombre") or "").strip() or "(sin nombre)"
        precio = r.get("precio")
        tallas = r.get("tallas") or []
        if isinstance(tallas, list):
            ts = ", ".join(str(x) for x in tallas)
        else:
            ts = str(tallas)
        desc = str(r.get("descripcion") or "").strip()
        if len(desc) > 100:
            desc = desc[:100] + "..."
        foto = str(r.get("foto_url") or "").strip()
        extra = f"\n  {desc}" if desc else ""
        if foto:
            extra += f"\n  foto: {foto[:80]}"
        lines.append(f"• {nom}\n  id: {tid} — precio: {precio}\n  Tallas: {ts}{extra}")
    body = "\n\n".join(lines)
    return (
        f"Leila Store — Catálogo\n\n{body}\n\nPedido: /pedido id_producto talla"
    


    )
def execute_leila_pedido(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
    username: str = "",
) -> str:
    """/pedido <producto_id> <talla> [nota] — inserta en leila_orders (shared.main si hay catálogo compartido)."""
    parts = (args or "").strip().split(None, 2)
    if len(parts) < 2:
        return "Uso: /pedido id_producto talla [nota opcional]"
    product_id = parts[0].strip()
    talla = parts[1].strip()
    nota = (parts[2].strip() if len(parts) > 2 else "") or ""
    cid = str(chat_id if chat_id is not None else "").strip() or "unknown"

    def _esc(s: str) -> str:
        return (s or "").replace("'", "''")[:2000]

    pid_sql = _esc(product_id)
    talla_sql = _esc(talla)
    nota_sql = _esc(nota)
    cid_sql = _esc(cid)
    prod_rel = _leila_products_rel(db)
    ord_rel = _leila_orders_rel(db)
    try:
        chk = db.query(f"SELECT nombre, activo FROM {prod_rel} WHERE id = '{pid_sql}' LIMIT 1")
        rows = json.loads(chk) if isinstance(chk, str) else (chk or [])
        if not rows or not isinstance(rows[0], dict):
            return f"No encontré el producto {product_id}. Usa /catalogo para ver ids."
        act = rows[0].get("activo")
        if act is False:
            return "Ese producto no está disponible."
        nombre = str(rows[0].get("nombre") or product_id)
        db.execute(
            f"INSERT INTO {ord_rel} (chat_id, producto_id, talla, nota) "
            f"VALUES ('{cid_sql}', '{pid_sql}', '{talla_sql}', '{nota_sql}')"
        )
    except Exception as e:
        return f"No pude registrar el pedido: {e}"

    user_label = (username or "").strip() or (str(requester_id).strip() if requester_id is not None else cid)
    admin_txt = f"Nuevo pedido: {nombre} talla {talla} de {user_label}"

    admin_chat = (
        (os.environ.get("DUCKCLAW_LEILA_ADMIN_CHAT_ID") or os.environ.get("DUCKCLAW_ADMIN_CHAT_ID") or "")
        .strip()
    )
    if admin_chat:
        tid = str(tenant_id or "default").strip() or "default"
        send_telegram_dm(
            admin_chat,
            f"🛍️ {admin_txt}",
            username=str(user_label),
            db=db,
            tenant_id=tid,
        )

    return (
        f"Pedido recibido: {nombre}, talla {talla}. Te contactamos pronto."
    


    )
def execute_leila_ayuda() -> str:
    """/ayuda — comprar en Leila Store (solo gateway Leila)."""
    return (
        "Leila Store — cómo comprar\n\n"
        "• /catalogo — ver productos, tallas y precios\n"
        "• /pedido id talla — registrar tu pedido (opcional: una nota al final)\n"
        "• Pregunta por tallas o combinar piezas; si algo es especial, dilo y lo vemos con Leila.\n\n"
        "Comandos generales del bot: /help"
    


    )
def execute_help(db: Any, chat_id: Any) -> str:
    """/help: lista los fly commands disponibles."""
    lines = [
        ("/team", "Whitelist + grants bases compartidas (--shared-*)"),
        ("/vault", "Bóvedas privadas: ver/listar/crear/cambiar/eliminar"),
        ("/workers", "Equipo (templates): ver o definir workers para este chat"),
        ("/roles", "Ver todos los trabajadores virtuales (templates)"),
        ("/tasks", "Estado actual: BUSY/IDLE, subagente, tarea"),
        ("/history", "Historial de tareas (quién hizo qué)"),
        ("/goals", "Objetivos de homeostasis"),
        ("/prompt <worker_id>", "Ver prompt; --change <texto> para cambiar"),
        ("/model", "Ver o cambiar LLM (provider/model)"),
        ("/skills <worker_id>", "Herramientas del template"),
        ("/forget", "Borrar historial de la conversación"),
        ("/context", "on|off (historial); en Telegram: --add / --summary (memoria semántica)"),
        ("/sandbox", "Toggle ejecución de código (true|false) para esta sesión"),
        ("/sandox", "(Alias) /sandbox para tolerar errores de escritura."),
        ("/heartbeat", "Activa mensajes en tiempo real mientras el agente trabaja"),
        ("/audit", "Última auditoría de ejecución"),
        ("/health", "Estado del servicio"),
        ("/sensors", "DuckDB, IBKR, Lake, Tavily, Reddit, Trends, browser sandbox"),
        ("/new_mind", "The Mind: crear partida (alias de /new_game the_mind)"),
        ("/join <game_id>", "The Mind: unirse a partida"),
        ("/start_mind [game_id]", "The Mind: iniciar y repartir Nivel 1"),
        ("/game", "The Mind: listar partidas waiting/playing"),
        ("/play <n>", "The Mind: jugar carta"),
        ("/cards", "The Mind: ver tus cartas activas (DM)"),
        ("/shuriken", "The Mind: votar uso de estrella ninja"),
        ("/setup", "Config key=value"),
        ("/approve", "Aprobar última acción"),
        ("/reject", "Rechazar última acción"),
        ("/execute_signal <uuid>", "Finanz quant: confirma ejecución de orden (HITL)"),
        ("/lake", "Estado del túnel SSH Capadonna (env + prueba rápida)"),
    ]
    if _leila_fly_commands_enabled():
        lines.extend(
            [
                ("/catalogo", "Leila: ver catálogo de productos"),
                ("/pedido id talla", "Leila: registrar pedido"),
                ("/ayuda", "Leila: cómo comprar"),
            ]
        )
    block = "\n".join(f"- {cmd} — {desc}" for cmd, desc in lines)
    return f"🦆 Fly commands:\n\n{block}"


def _fly_reply_preview(s: str, max_len: int = 120) -> str:
    """Resumen de respuesta para [FLY] sin volcar secretos ni bloques enormes."""
    t = (s or "").replace("\n", " ").strip()
    if len(t) > max_len:
        return t[:max_len] + "..."
    return t


def _ssh_reach_icon(reach: str) -> str:
    r = (reach or "").lower()
    if "alcanzable" in r and "ok" in r:
        return "✅"
    if "no probado" in r or "falta config" in r:
        return "⚠️"
    return "❌"


def _capadonna_lake_status_lines(*, compact: bool) -> list[str]:
    """Líneas de diagnóstico Lake Capadonna (misma lógica que /lake; compact para /sensors)."""
    from duckclaw.forge.skills.quant_market_bridge import (
        capadonna_ssh_config_ok,
        lake_belief_observed_values,
        _resolved_identity_file,
    )

    host = (os.environ.get("CAPADONNA_SSH_HOST") or "").strip()
    user = (os.environ.get("CAPADONNA_SSH_USER") or "capadonna").strip()
    cmd_set = bool((os.environ.get("CAPADONNA_REMOTE_OHLC_CMD") or "").strip())
    idp = _resolved_identity_file()
    strict = capadonna_ssh_config_ok()
    host_v, online_v = lake_belief_observed_values()
    reach = "no probado (falta config)"
    if strict and host:
        ssh_args: list[str] = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
        if idp:
            ssh_args.extend(["-i", idp])
        ssh_args.extend([f"{user}@{host}", "true"])
        try:
            proc = subprocess.run(ssh_args, capture_output=True, text=True, timeout=20)
            if proc.returncode == 0:
                reach = "alcanzable (ssh true OK)"
            else:
                err = (proc.stderr or proc.stdout or "").strip()[:200]
                reach = f"fallo rc={proc.returncode}" + (f" — {err}" if err else "")
        except FileNotFoundError:
            reach = "ssh no encontrado en PATH"
        except subprocess.TimeoutExpired:
            reach = "timeout 20s"
        except Exception as e:
            reach = str(e)[:120]
    if compact:
        icfg = "✅" if strict else "⚠️"
        ireach = _ssh_reach_icon(reach)
        return [
            "🌊 Lake Capadonna · SSH / Tailscale",
            f"   {icfg} Config operativa: {'sí' if strict else 'no'} · CAPADONNA_SSH_HOST: {'sí' if host else 'no'}",
            f"   📊 Creencias 0/1: lake_host_configured≈{int(host_v)} · lake_status_online≈{int(online_v)}",
            f"   {ireach} Alcance SSH (rápido): {reach}",
        ]
    lines = [
        "Capadonna Lake (SSH)",
        f"- CAPADONNA_SSH_HOST: {'sí' if host else 'no'}",
        f"- CAPADONNA_SSH_USER: {user}",
        f"- CAPADONNA_REMOTE_OHLC_CMD: {'sí' if cmd_set else 'no'}",
        f"- Clave SSH (-i): {idp or '(no definida / ssh-agent)'}",
        f"- Config lista para intentar: {'sí' if strict else 'no'}",
        f"- Semántica creencias (0/1): lake_host_configured≈{int(host_v)} lake_status_online≈{int(online_v)}",
        f"- Alcance SSH rápido: {reach}",
    ]
    return lines


def _probe_ibkr_portfolio(timeout_s: float = 8.0) -> str:
    api_url = os.environ.get("IBKR_PORTFOLIO_API_URL", "").strip()
    api_key = os.environ.get("IBKR_PORTFOLIO_API_KEY", "").strip()
    if not api_url or not api_key:
        return "Portafolio: no configurado (IBKR_PORTFOLIO_API_URL o IBKR_PORTFOLIO_API_KEY)"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    req = urllib.request.Request(api_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            if resp.status != 200:
                return f"Portafolio: HTTP {resp.status}"
            return "Portafolio: OK (HTTP 200, JSON)"
    except urllib.error.HTTPError as e:
        return f"Portafolio: HTTP {e.code}"[:80]
    except urllib.error.URLError as e:
        return f"Portafolio: red — {e.reason!s}"[:100]
    except Exception as e:
        return f"Portafolio: {str(e)[:80]}"


def _sensor_line_bullet(icon: str, text: str) -> str:
    """Una línea de detalle bajo un bloque /sensors (icono + texto)."""
    t = (text or "").strip()
    return f"   {icon} {t}" if t else f"   {icon}"


def _ibkr_detail_icon(line: str) -> str:
    low = (line or "").lower()
    if "no configurado" in low:
        return "⚠️"
    if "http 404" in low:
        return "⚠️"
    if ": ok" in low or " ok " in low:
        return "✅"
    if "http 200" in low:
        return "✅"
    return "❌"


def _probe_ibkr_market_data(timeout_s: float = 8.0) -> str:
    base = (os.environ.get("IBKR_MARKET_DATA_URL") or "").strip()
    if not base:
        return "Mercado OHLC: no configurado (IBKR_MARKET_DATA_URL)"
    q = urllib.parse.urlencode({"ticker": "SPY", "timeframe": "1d", "lookback_days": "3"})
    url = f"{base}&{q}" if "?" in base else f"{base}?{q}"
    req = urllib.request.Request(url, method="GET")
    token = (
        os.environ.get("IBKR_PORTFOLIO_API_KEY") or os.environ.get("IBKR_MARKET_DATA_API_KEY") or ""
    ).strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return "Mercado OHLC: respuesta no JSON"
        if isinstance(payload, dict):
            err = payload.get("error") or payload.get("message")
            if err and isinstance(err, str) and err.strip():
                return f"Mercado OHLC: API — {err.strip()[:80]}"
        return "Mercado OHLC: OK (JSON)"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return (
                "Mercado OHLC: HTTP 404 — la URL no existe en el API "
                "(Capadonna :8002 no expone aún OHLC por HTTP). "
                "Histórico 1d/1w/1M/moc vía lake SSH está bien; "
                "intradía necesita ese endpoint o quita IBKR_MARKET_DATA_URL del .env."
            )[:280]
        return f"Mercado OHLC: HTTP {e.code}"[:80]
    except urllib.error.URLError as e:
        return f"Mercado OHLC: red — {e.reason!s}"[:100]
    except Exception as e:
        return f"Mercado OHLC: {str(e)[:80]}"


def _browser_sandbox_sensor_lines() -> list[str]:
    """Líneas compactas para /sensors: manifest finanz, Docker, imagen browser, red en policy."""
    lines: list[str] = [
        "🌐 Browser sandbox · Playwright (`run_browser_sandbox`)",
    ]
    mf_bs: bool | None = None
    try:
        from duckclaw.workers.manifest import load_manifest

        mf_bs = bool(load_manifest("finanz").browser_sandbox)
    except Exception:
        mf_bs = None

    if mf_bs is None:
        lines.append(_sensor_line_bullet("⚠️", "No se pudo leer manifest finanz (browser_sandbox)"))
    elif mf_bs:
        lines.append(_sensor_line_bullet("✅", "Worker finanz: browser_sandbox=true"))
    else:
        lines.append(_sensor_line_bullet("⚠️", "Worker finanz: browser_sandbox=false — tool no registrada"))

    net_mode: str | None = None
    try:
        from duckclaw.forge import WORKERS_TEMPLATES_DIR
        from duckclaw.forge.schema import load_security_policy

        pol = load_security_policy("finanz", worker_dir=WORKERS_TEMPLATES_DIR / "finanz")
        net_mode = "bridge" if pol.network.default != "deny" else "deny"
        if net_mode == "deny":
            lines.append(
                _sensor_line_bullet(
                    "⚠️",
                    "security_policy finanz: red=deny — Playwright no podrá abrir URLs HTTP",
                )
            )
    except Exception:
        net_mode = None

    try:
        from duckclaw.graphs.sandbox import _browser_image_name, _docker_available
    except Exception as exc:
        lines.append(_sensor_line_bullet("❌", f"Sandbox no importable — {exc!s}"[:120]))
        return lines

    if not _docker_available():
        lines.append(_sensor_line_bullet("❌", "Docker no responde — run_browser_sandbox no arrancará"))
        return lines

    lines.append(_sensor_line_bullet("✅", "Docker ping OK"))

    img = _browser_image_name()
    env_override = bool((os.environ.get("STRIX_BROWSER_IMAGE") or "").strip())
    label = f"{img}" + (" · STRIX_BROWSER_IMAGE" if env_override else "")

    try:
        import docker  # noqa: PLC0415

        client = docker.from_env()
        client.images.get(img)
        lines.append(_sensor_line_bullet("✅", f"Imagen local · {label}"[:140]))
    except Exception:
        lines.append(
            _sensor_line_bullet(
                "⚠️",
                f"Imagen no encontrada localmente · {label} — build/pull antes del primer uso",
            )[:200]
        )

    if net_mode == "bridge":
        lines.append(_sensor_line_bullet("✅", "Policy red: bridge (HTTP permitido en contenedor browser)"))

    return lines


def execute_sensors(db: Any) -> str:
    """/sensors: resumen DuckDB, IBKR, Lake, Tavily, Reddit, Google Trends, browser sandbox (proceso gateway)."""
    blocks: list[str] = ["📡 Sensores Finanz", "═══════════════════════", ""]

    try:
        db.query("SELECT 1")
        blocks.append("🦆 DuckDB local")
        blocks.append(_sensor_line_bullet("✅", "Conectado · SELECT 1 OK"))
    except Exception as e:
        blocks.append("🦆 DuckDB local")
        blocks.append(_sensor_line_bullet("❌", f"Error — {str(e)[:100]}"))

    blocks.append("")
    blocks.append("🏦 IBKR (gateway)")
    p_line = _probe_ibkr_portfolio()
    m_line = _probe_ibkr_market_data()
    blocks.append(_sensor_line_bullet(_ibkr_detail_icon(p_line), p_line))
    blocks.append(_sensor_line_bullet(_ibkr_detail_icon(m_line), m_line))

    blocks.append("")
    try:
        blocks.extend(_capadonna_lake_status_lines(compact=True))
    except Exception as e:
        blocks.append("🌊 Lake Capadonna")
        blocks.append(_sensor_line_bullet("❌", f"Error — {str(e)[:100]}"))

    blocks.append("")
    try:
        from duckclaw.forge.skills.research_bridge import _tavily_available
    except Exception:
        _tavily_available = lambda: False  # type: ignore[misc, assignment]

    tav_pkg = False
    try:
        import tavily  # noqa: F401

        tav_pkg = True
    except ImportError:
        pass
    tav_key = bool((os.environ.get("TAVILY_API_KEY") or "").strip())
    tav_ready = bool(_tavily_available())
    blocks.append("🔎 Tavily (research)")
    if tav_ready and tav_pkg and tav_key:
        blocks.append(_sensor_line_bullet("✅", "Listo · paquete · TAVILY_API_KEY · bridge"))
    elif not tav_pkg and not tav_key:
        blocks.append(_sensor_line_bullet("⚠️", "Sin paquete tavily ni clave"))
    else:
        blocks.append(
            _sensor_line_bullet(
                "⚠️",
                f"Parcial · paquete={'sí' if tav_pkg else 'no'} · clave={'sí' if tav_key else 'no'} · bridge={'sí' if tav_ready else 'no'}",
            )
        )

    blocks.append("")
    try:
        from duckclaw.forge.skills.reddit_bridge import _mcp_available, _reddit_env_ready
    except Exception:
        redd_mcp = False
        redd_env = False
    else:
        redd_mcp = _mcp_available()
        redd_env = _reddit_env_ready()
    npx_ok = shutil.which("npx") is not None
    blocks.append("📣 Reddit · mcp-reddit")
    if redd_mcp and redd_env and npx_ok:
        blocks.append(_sensor_line_bullet("✅", "Librería MCP · env Reddit · npx en PATH"))
    else:
        blocks.append(
            _sensor_line_bullet(
                "⚠️",
                f"mcp_lib={'sí' if redd_mcp else 'no'} · env={'sí' if redd_env else 'no'} · npx={'sí' if npx_ok else 'no'}",
            )
        )

    blocks.append("")
    try:
        from duckclaw.forge.skills.google_trends_bridge import (
            _default_stdio_command_and_args,
            _mcp_available as _gt_mcp_ok,
        )
    except Exception:
        gt_cmd = ""
        gt_args: list[str] = []
        gt_mcp = False
    else:
        gt_mcp = _gt_mcp_ok()
        gt_cmd, gt_args = _default_stdio_command_and_args()
    blocks.append("📈 Google Trends MCP")
    if not gt_cmd:
        blocks.append(_sensor_line_bullet("⚠️", "Stdio no resuelto (google-trends-mcp / uvx en PATH)"))
    else:
        arg_hint = f" {' '.join(gt_args)}" if gt_args else ""
        tid = "✅" if gt_mcp else "⚠️"
        blocks.append(
            _sensor_line_bullet(
                tid,
                f"mcp_lib={'sí' if gt_mcp else 'no'} · stdio: {gt_cmd}{arg_hint}",
            )
        )

    blocks.append("")
    try:
        blocks.extend(_browser_sandbox_sensor_lines())
    except Exception as e:
        blocks.append("🌐 Browser sandbox · Playwright (`run_browser_sandbox`)")
        blocks.append(_sensor_line_bullet("❌", f"Error — {str(e)[:100]}"))

    return "\n".join(blocks)


def execute_lake_status() -> str:
    """/lake [status]: variables Capadonna y prueba SSH corta (BatchMode, ConnectTimeout=5)."""
    try:
        lines = _capadonna_lake_status_lines(compact=False)
    except Exception as e:
        return f"Lake: no se pudo cargar el bridge quant: {e}"
    return "\n".join(lines)


def execute_quant_execute_signal(chat_id: Any, args: str) -> str:
    """/execute_signal <uuid>: autoriza una llamada a execute_order (HITL) para Finanz quant."""
    sid = (args or "").strip().lower()
    if not re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        sid,
    ):
        return "Uso: /execute_signal <signal_id_UUID>"
    try:
        from duckclaw.graphs.graph_server import get_db as _get_db

        _db = _get_db()
        tid = str(get_chat_state(_db, chat_id, "tenant_id") or "default").strip() or "default"
        rid = str(get_chat_state(_db, chat_id, "last_requester_id") or "").strip()
        if _is_wr_tenant(tid):
            clearance = _wr_member_clearance(_db, tenant_id=tid, user_id=rid)
            if not (_is_gateway_owner_user(rid) or clearance == "admin"):
                return "❌ Acceso denegado: /execute_signal en War Room requiere clearance admin."
    except Exception:
        pass
    try:
        from duckclaw.forge.skills.quant_hitl import grant_execute_order

        grant_execute_order(str(chat_id).strip(), sid)
    except Exception as e:
        return f"No se pudo registrar la confirmación: {e}"
    return (
        f"Confirmación registrada para la señal {sid}. "
        "Pide al asistente que ejecute la herramienta execute_order con ese signal_id en esta sesión."
    


    )
def _dispatch_fly_command(
    db: Any,
    chat_id: Any,
    name: str,
    args: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
    vault_user_id: Any = None,
    username: str = "",
) -> Optional[str]:
    """Ejecuta un comando fly ya parseado (sin contexto de logging)."""
    if name == "sensors":
        return execute_sensors(db)
    if name == "lake":
        sub = (args or "").strip().lower()
        if sub in ("", "status"):
            return execute_lake_status()
        return "Uso: /lake o /lake status"
    if name == "execute_signal":
        return execute_quant_execute_signal(chat_id, args)
    if name == "register_wr_member":
        return register_wr_member(db, tenant_id, requester_id, args)
    if name == "get_wr_context":
        return get_wr_context(db, tenant_id, args)
    if name == "broadcast_alert":
        return broadcast_alert(db, tenant_id, requester_id, args)
    if name == "catalogo" and _leila_fly_commands_enabled():
        return execute_leila_catalogo(db, chat_id)
    if name == "pedido" and _leila_fly_commands_enabled():
        return execute_leila_pedido(
            db, chat_id, args, requester_id=requester_id, tenant_id=tenant_id, username=username
        )
    if name == "ayuda" and _leila_fly_commands_enabled():
        return execute_leila_ayuda()
    if name == "help":
        return execute_help(db, chat_id)
    if name == "role":
        return (
            "El comando /role ya no existe. Usa /workers para ver o definir el equipo, /help para ver todos los comandos."
        
        )
    if name == "roles":
        return execute_roles(db, chat_id)
    if name == "team":
        return execute_team_whitelist(db, tenant_id, requester_id, args)
    if name == "vault":
        return execute_vault(
            args,
            vault_user_id=vault_user_id or requester_id or chat_id,
            tenant_id=tenant_id,
            db=db,
        )
    if name == "workers":
        return execute_team(
            db, chat_id, args, tenant_id=tenant_id, requester_id=requester_id
        )
    if name == "skills":
        return execute_skills_list(db, chat_id, args)
    if name == "forget":
        return execute_forget(db, chat_id)
    if name == "start_mind":
        return execute_start_mind(
            db, chat_id, args, requester_id=requester_id, tenant_id=tenant_id
        )
    if name == "new_mind":
        return execute_new_game(
            db, chat_id, "the_mind", requester_id=requester_id, tenant_id=tenant_id
        )
    if name == "new_game":
        return execute_new_game(
            db, chat_id, args, requester_id=requester_id, tenant_id=tenant_id
        )
    if name == "join":
        return execute_join_game(
            db, chat_id, args, requester_id=requester_id, tenant_id=tenant_id
        )
    if name == "game":
        return execute_list_mind_games(
            db,
            chat_id,
            args,
            requester_id=requester_id,
            tenant_id=tenant_id,
        )
    if name == "start_game":
        return execute_start_game(db, chat_id, args)
    if name == "deal":
        return execute_deal(db, chat_id, args)
    if name == "play":
        return execute_play_mind(db, chat_id, args, tenant_id=tenant_id)
    if name == "cards":
        return execute_cards(db, chat_id, args)
    if name == "shuriken":
        return execute_shuriken(db, chat_id, args, tenant_id=tenant_id)
    if name == "context":
        return execute_context_toggle(db, chat_id, args)
    if name in ("sandbox", "sandox"):
        return execute_sandbox_toggle(db, chat_id, args)
    if name == "heartbeat":
        return execute_heartbeat(db, chat_id, args, tenant_id=tenant_id)
    if name == "audit":
        return execute_audit(db, chat_id)
    if name == "health":
        return execute_health(db)
    if name == "approve":
        return execute_approve_reject(db, chat_id, True)
    if name == "reject":
        return execute_approve_reject(db, chat_id, False)
    if name in ("prompt", "system_prompt", "system"):
        return execute_prompt(db, chat_id, args)
    if name in ("model", "provider", "llm"):
        return execute_model(db, chat_id, args)
    if name == "setup":
        return _execute_setup(db, chat_id, args)
    if name == "goals":
        return execute_goals(db, chat_id, args)
    if name == "tasks":
        return execute_tasks(db, chat_id)
    if name == "history":
        return execute_history(db, chat_id, args)
    return None


def execute_shuriken(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: Any = None,
) -> str:
    """/shuriken: voto para usar estrella ninja. Se aplica cuando votan todos los jugadores activos."""
    _ = args
    try:
        _ensure_the_mind_schema(db)
        tid = str(tenant_id or "default").strip() or "default"
        cid = str(chat_id).replace("'", "''")[:256]
        rows = list(
            db.execute(
                """
                SELECT g.game_id, g.current_level, g.shurikens, g.status, p.username
                FROM the_mind_games g
                JOIN the_mind_players p ON p.game_id = g.game_id
                WHERE g.status = 'playing' AND p.chat_id = ?
                ORDER BY g.rowid DESC
                LIMIT 1
                """,
                (cid,),
            )
        )
        if not rows:
            return "No encontré ninguna partida en juego asociada a este chat."
        game_id, lvl, stars, status, uname = rows[0]
        if str(status or "").strip().lower() != "playing":
            return "La partida no está en juego."
        stars_i = int(stars or 0)
        if stars_i <= 0:
            return "No quedan estrellas disponibles."

        player_rows = list(
            db.execute("SELECT chat_id, username, cards FROM the_mind_players WHERE game_id = ?", (game_id,))
        )
        if not player_rows:
            return "No hay jugadores en esta partida."
        active_players = [(str(r[0] or ""), str(r[1] or ""), list(r[2] or [])) for r in player_rows]
        active_chat_ids = [p[0] for p in active_players if p[0]]
        if cid not in active_chat_ids:
            return "No estás registrado en esta partida."

        vote_rows = list(
            db.execute(
                """
                SELECT DISTINCT chat_id
                FROM the_mind_moves
                WHERE game_id = ? AND move_type = 'shuriken_vote' AND level = ?
                """,
                (game_id, int(lvl or 1)),
            )
        )
        votes = {str(v[0] or "") for v in vote_rows if v and v[0]}
        if cid not in votes:
            _insert_mind_move(
                db,
                game_id=str(game_id),
                chat_id=cid,
                username=str(uname or ""),
                move_type="shuriken_vote",
                level=int(lvl or 1),
            )
            votes.add(cid)

        active_set = {p[0] for p in active_players if p[0]}
        if votes >= active_set:
            discarded_parts: list[str] = []
            for pchat, puname, cards in active_players:
                if not cards:
                    continue
                lowest = min(cards)
                # Quitar una sola ocurrencia de la menor
                removed = False
                final_cards: list[int] = []
                for c in cards:
                    if not removed and c == lowest:
                        removed = True
                        continue
                    final_cards.append(c)
                db.execute(
                    "UPDATE the_mind_players SET cards = ? WHERE game_id = ? AND chat_id = ?",
                    (final_cards, game_id, pchat),
                )
                discarded_parts.append(
                    f"{_player_label(puname, pchat, db=db, tenant_id=tid)} descartó el {lowest}"
                )
                _insert_mind_move(
                    db,
                    game_id=str(game_id),
                    chat_id=str(pchat),
                    username=str(puname or ""),
                    move_type="shuriken_discard",
                    card_value=int(lowest),
                    level=int(lvl or 1),
                )
            new_stars = max(stars_i - 1, 0)
            db.execute("UPDATE the_mind_games SET shurikens = ? WHERE game_id = ?", (new_stars, game_id))
            try:
                broadcast_message_to_players(
                    db,
                    game_id,
                    f"⭐ Estrella usada. {', '.join(discarded_parts)}. Estrellas restantes: {new_stars}",
                    exclude_chat_id=cid,
                )
            except Exception:
                pass
            return (
                f"⭐ Estrella usada. {', '.join(discarded_parts)}. Estrellas restantes: {new_stars}"
            

            )
        actor = _player_label(uname, cid, db=db, tenant_id=tid)
        for pchat, puser, _ in active_players:
            if pchat and pchat != cid:
                send_telegram_dm(
                    pchat,
                    f"{actor} quiere usar la estrella. Envía /shuriken para confirmar.",
                    username=str(puser or ""),
                    db=db,
                    tenant_id=tid,
                )
        return "⭐ Voto registrado. Esperando a los demás..."
    except Exception as e:
        return f"No se pudo procesar /shuriken: {e}"


def handle_command(
    db: Any,
    chat_id: Any,
    text: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
    vault_user_id: Any = None,
    username: str = "",
) -> Optional[str]:
    """
    Middleware: si el mensaje es un comando on-the-fly, ejecuta y retorna la respuesta.
    Si no es comando o no es manejado, retorna None.
    """
    name, args = parse_command(text)
    if not name:
        return None
    tid = str(tenant_id or "default").strip() or "default"
    try:
        cid = str(chat_id if chat_id is not None else "unknown").strip() or "unknown"
    except Exception:
        cid = "unknown"
    chat_ident = _chat_log_identity_for_context(chat_id, db=db, tenant_id=tid)
    _fly_log = get_obs_logger("duckclaw.fly")
    with structured_log_context(tenant_id=tid, worker_id="gateway", chat_id=chat_ident):
        try:
            set_chat_state(db, chat_id, "tenant_id", tid)
            if requester_id is not None:
                set_chat_state(db, chat_id, "last_requester_id", str(requester_id).strip())
        except Exception:
            pass
        out = _dispatch_fly_command(
            db,
            chat_id,
            name,
            args,
            requester_id=requester_id,
            tenant_id=tenant_id,
            vault_user_id=vault_user_id,
            username=username or "",
        )
        if out is not None:
            log_fly(_fly_log, "/%s -> %s", name, _fly_reply_preview(out))
        return out


def _execute_setup(db: Any, chat_id: Any, args: str) -> str:
    """/setup [key=value | key=value]: formato compatible con Telegram. Sin args muestra config."""
    if not args or not args.strip():
        p = get_chat_state(db, chat_id, "llm_provider") or _get_global_config(db, "llm_provider")
        m = get_chat_state(db, chat_id, "llm_model") or _get_global_config(db, "llm_model")
        wid = get_chat_state(db, chat_id, "worker_id")
        prompt = _get_global_config(db, "system_prompt") or ""
        return (
            f"Config actual:\n- llm_provider: {p or '—'}\n- llm_model: {m or '—'}\n"
            f"- worker_id: {wid or '—'}\n- system_prompt: {prompt[:80]}...\n\n"
            "Para cambiar: /setup llm_provider=deepseek | /setup system_prompt=..."
        
        )
    for part in args.split("|"):
        part = part.strip()
        if "=" in part:
            k, _, v = part.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k in ("llm_provider", "provider"):
                if v and v.lower() not in _PROVIDERS:
                    return f"Provider desconocido: {v}. Válidos: {', '.join(_PROVIDERS)}"
                set_chat_state(db, chat_id, "llm_provider", v)
                if v.lower() == "mlx":
                    from duckclaw.integrations.llm_providers import mlx_openai_compatible_base_url

                    set_chat_state(db, chat_id, "llm_base_url", mlx_openai_compatible_base_url())
                    mid = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
                    set_chat_state(db, chat_id, "llm_model", mid)
                else:
                    default_model = _DEFAULT_MODEL_BY_PROVIDER.get(v.lower(), "")
                    set_chat_state(db, chat_id, "llm_model", default_model)
                    default_url = _DEFAULT_BASE_URL_BY_PROVIDER.get(v.lower(), "")
                    if default_url:
                        set_chat_state(db, chat_id, "llm_base_url", default_url)
                    else:
                        set_chat_state(db, chat_id, "llm_base_url", "")
            elif k in ("llm_model", "model"):
                set_chat_state(db, chat_id, "llm_model", v)
            elif k in ("llm_base_url", "base_url"):
                set_chat_state(db, chat_id, "llm_base_url", v)
            elif k in ("system_prompt", "prompt"):
                _set_global_config(db, "system_prompt", v)
    return "✅ Config actualizado."


def get_history_limit_for_chat(db: Any, chat_id: Any, default: int = 10) -> int:
    """Devuelve el límite de historial según use_rag del chat (para /context off = menos contexto)."""
    use_rag = get_chat_state(db, chat_id, "use_rag")
    if use_rag == "false":
        return 3
    return default


def get_worker_id_for_chat(db: Any, chat_id: Any) -> str:
    """Devuelve el worker_id asignado a este chat. Por defecto: manager (orquesta y delega a templates)."""
    return get_chat_state(db, chat_id, "worker_id") or _DEFAULT_WORKER


def save_last_audit(db: Any, chat_id: Any, latency_ms: int, sql: str = "", run_id: str = "", tokens: Any = None) -> None:
    """Guarda datos de la última ejecución para /audit."""
    data = {"latency_ms": latency_ms, "sql": sql or "", "run_id": run_id or "", "tokens": tokens or ""}
    set_chat_state(db, chat_id, "last_audit", json.dumps(data))


_TASK_AUDIT_TABLE = "task_audit_log"


def _ensure_task_audit_log(db: Any) -> None:
    """Crea task_audit_log y aplica migraciones suaves (plan_title)."""
    if _skip_runtime_ddl(db):
        return
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TASK_AUDIT_TABLE} (
            task_id VARCHAR PRIMARY KEY,
            tenant_id VARCHAR NOT NULL,
            worker_id VARCHAR,
            query_prefix VARCHAR,
            status VARCHAR NOT NULL,
            duration_ms INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            plan_title VARCHAR
        )
        """
    )
    # Migración suave: añadir plan_title si la tabla existe sin esta columna (bases antiguas)
    try:
        info = db.query(f"PRAGMA table_info({_TASK_AUDIT_TABLE})")
        rows = json.loads(info) if isinstance(info, str) else (info or [])
        cols = {str(r.get("name") or "") for r in rows if isinstance(r, dict)}
        if "plan_title" not in cols:
            db.execute(f"ALTER TABLE {_TASK_AUDIT_TABLE} ADD COLUMN plan_title VARCHAR")
    except Exception:
        # No romper si PRAGMA/ALTER falla; la feature seguirá funcionando sin plan_title persistente.
        pass


def _infer_user_id_for_audit_queue(db_path: str) -> str:
    """Alineado con validate_user_db_path: slug bajo db/private/{user}/."""
    from pathlib import Path

    parts = Path(db_path).expanduser().resolve().parts
    if "private" in parts:
        i = parts.index("private")
        if i + 1 < len(parts):
            return str(parts[i + 1])
    return "default"


def append_task_audit(
    db: Any,
    tenant_id: Any,
    worker_id: str,
    query_prefix: str,
    status: str,
    duration_ms: int,
    plan_title: Optional[str] = None,
) -> None:
    """Append a task to task_audit_log for /history. plan_title es el identificador semántico para auditoría y /history."""
    import uuid

    _ensure_task_audit_log(db)
    task_id = f"TASK-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
    tenant_s = str(tenant_id).replace("'", "''")[:128]
    worker_s = (worker_id or "").replace("'", "''")[:64]
    prefix_s = (query_prefix or "")[:256].replace("'", "''")
    status_s = (status or "SUCCESS").upper().replace("'", "''")[:32]
    status_allowed = ("SUCCESS", "FAILED", "PROACTIVE_MESSAGE_SENT", "SECURITY_VIOLATION_ATTEMPT")
    status_s = "SUCCESS" if status_s not in status_allowed else status_s
    plan_title_s = (plan_title or "")[:256].replace("'", "''") if plan_title else ""
    sql = (
        f"""
        INSERT INTO {_TASK_AUDIT_TABLE} (task_id, tenant_id, worker_id, query_prefix, status, duration_ms, plan_title)
        VALUES ('{task_id}', '{tenant_s}', '{worker_s}', '{prefix_s}', '{status_s}', {int(duration_ms)}, '{plan_title_s}')
        """
    )
    if _skip_runtime_ddl(db):
        try:
            from pathlib import Path

            from duckclaw.db_write_queue import enqueue_duckdb_write_sync

            raw_path = str(getattr(db, "_path", "") or "").strip()
            if not raw_path:
                return
            resolved = str(Path(raw_path).expanduser().resolve())
            uid = _infer_user_id_for_audit_queue(resolved)
            enqueue_duckdb_write_sync(
                db_path=resolved,
                query=sql.strip(),
                user_id=uid,
                tenant_id=str(tenant_id or "default").strip() or "default",
            )
        except Exception:
            pass
        return
    db.execute(sql)


def _is_simple_greeting(prefix: str) -> bool:
    """True si el mensaje es un saludo corto (hola, hi, etc.) sin tarea real."""
    p = (prefix or "").strip().lower()[:50]
    if len(p) > 35:
        return False
    greetings = (
        "hola", "hi", "hey", "hello", "buenas", "qué tal", "que tal",
        "buenos días", "buenos dias", "buenas tardes", "buenas noches",
        "ola", "saludos", "ciao", "adios", "chao",
    )
    return p in greetings or p.rstrip("!?.") in greetings


_CAPABILITIES_SMALLTALK = re.compile(
    r"""^[\s¿¡]*(
  qu[eé]\s+puedes\s+hacer(\s+ahora|\s+por\s+m[ií]|\s+por\s+nosotros)? |
  qu[eé]\s+sabes\s+hacer |
  en\s+qu[eé]\s+puedes\s+ayud(ar|arme) |
  qu[eé]\s+puedes\s+ofrec(er|erme) |
  cu[aá]les\s+son\s+tus\s+capacidades |
  para\s+qu[eé]\s+sirves |
  qu[eé]\s+funciones\s+tienes |
  mu[eé]strame\s+qu[eé]\s+puedes(\s+hacer)? |
  what\s+can\s+you\s+do |
  how\s+can\s+you\s+help(\s+me)?
)[\s?!.]*$""",
    re.IGNORECASE | re.VERBOSE,
)

# Pedidos de ejemplo meta (sin dataset concreto): no invocar plan + worker
# Nota: ``pued(es|as|a|e)`` cubre «puedes», «puedas», «puede», «pueda» (no usar ``pueda?s?``, que no casa «puedes»).
_CAPABILITIES_EXAMPLE_SMALLTALK = re.compile(
    r"""^[\s¿¡]*(
  d[aá]me\s+(un\s+)?ejemplo(\s+de\s+algo)?\s+que\s+pued(es|as|a|e)\s+hacer |
  d[aá]me\s+un\s+ejemplo\s+de\s+lo\s+que\s+pued(es|as|a|e)\s+hacer |
  (mu[eé]strame|ens[eé][ñn]ame)\s+(un\s+)?ejemplo(\s+de\s+algo\s+que\s+pued(es|as|a|e)\s+hacer)? |
  (mu[eé]strame|ens[eé][ñn]ame)\s+un\s+ejemplo |
  ejemplo\s+de\s+algo\s+que\s+pued(es|as|a|e)\s+hacer |
  un\s+ejemplo\s+de\s+lo\s+que\s+pued(es|as|a|e)\s+hacer |
  pued(es|as|a|e)\s+dar(me)?\s+un\s+ejemplo |
  alg[uú]n\s+ejemplo\s+de\s+lo\s+que\s+pued(es|as|a|e)\s+hacer |
  give\s+me\s+an?\s+example(\s+of\s+what\s+you\s+can\s+do)? |
  show\s+me\s+an?\s+example
)[\s?!.]*$""",
    re.IGNORECASE | re.VERBOSE,
)


def _is_capabilities_smalltalk(text: str) -> bool:
    """
    True si el usuario pide capacidades o un ejemplo genérico de uso, en una frase corta,
    sin datos concretos (evita plan LLM + invoke_worker).
    """
    raw = (text or "").strip()
    if not raw or raw.startswith("/"):
        return False
    if len(raw) > 120:
        return False
    # Pregunta meta + pedido concreto: mejor pasar por el planner
    if re.search(
        r"\b(con|sobre|analiz|datos|tabla|tablas|sql|ventas|csv|duckdb|query|métrica|metrica|grafico|gráfico)\b",
        raw,
        re.I,
    ):
        return False
    return bool(_CAPABILITIES_SMALLTALK.match(raw) or _CAPABILITIES_EXAMPLE_SMALLTALK.match(raw))


def _is_complex_task(row: dict) -> bool:
    """True si la tarea usó herramientas (tool use) o no es un saludo simple."""
    prefix = (row.get("query_prefix") or "").strip()
    if _is_simple_greeting(prefix):
        return False
    try:
        dur_ms = int(row.get("duration_ms") or 0)
    except (TypeError, ValueError):
        dur_ms = 0
    return dur_ms >= 1500 or len(prefix) > 20


def execute_history(db: Any, chat_id: Any, args: str) -> str:
    """/history [n]: historial de tareas complejas (tool use). Saludos simples (hola) se muestran como máximo uno."""
    tenant_s = str(chat_id).replace("'", "''")[:128]
    try:
        n = int((args or "5").strip())
        n = max(1, min(n, 20))
    except ValueError:
        n = 5
    _ensure_task_audit_log(db)
    try:
        r = db.query(
            f"""
            SELECT task_id, query_prefix, status, duration_ms, created_at, worker_id, plan_title
            FROM {_TASK_AUDIT_TABLE}
            WHERE tenant_id = '{tenant_s}'
            ORDER BY created_at DESC
            LIMIT 100
            """
        )
        rows = json.loads(r) if isinstance(r, str) else (r or [])
    except Exception as e:
        return f"Error al cargar historial: {e}."

    if not rows:
        return "📋 Sin tareas registradas."

    # Filtrar: tareas complejas con título de plan + como máximo 1 saludo simple
    complex_rows = []
    one_greeting = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        plan_title_raw = (row.get("plan_title") or "").strip()
        if _is_complex_task(row) and plan_title_raw:
            complex_rows.append(row)
        elif one_greeting is None and _is_simple_greeting(row.get("query_prefix") or ""):
            one_greeting = row
    filtered = complex_rows[:n]
    if one_greeting is not None and len(filtered) < n:
        filtered.append(one_greeting)

    if not filtered:
        return "📋 Sin tareas complejas."

    # Evitar duplicados: si hay varias filas con mismo worker/status/duración y
    # solo algunas tienen plan_title explícito, preferir las que sí lo tienen.
    deduped = []
    for idx, row in enumerate(filtered):
        if not isinstance(row, dict):
            continue
        raw_plan = (row.get("plan_title") or "").strip()
        if not raw_plan:
            wid = (row.get("worker_id") or "").strip()
            status = (row.get("status") or "UNKNOWN").upper()
            try:
                dur_ms = int(row.get("duration_ms") or 0)
            except (TypeError, ValueError):
                dur_ms = 0
            has_better = False
            for j, other in enumerate(filtered):
                if j == idx or not isinstance(other, dict):
                    continue
                other_plan = (other.get("plan_title") or "").strip()
                if not other_plan:
                    continue
                wid2 = (other.get("worker_id") or "").strip()
                status2 = (other.get("status") or "UNKNOWN").upper()
                try:
                    dur2 = int(other.get("duration_ms") or 0)
                except (TypeError, ValueError):
                    dur2 = 0
                if wid2 == wid and status2 == status and dur2 == dur_ms:
                    has_better = True
                    break
            if has_better:
                continue
        deduped.append(row)

    if not deduped:
        return "📋 Sin tareas complejas."

    lines = [f"📋 Últimas {len(deduped)}"]
    for i, row in enumerate(deduped, 1):
        if not isinstance(row, dict):
            continue
        prefix = (row.get("query_prefix") or "").strip()[:80]
        # Título del plan (guardado por el Manager): se muestra después del subagente
        plan_title = (row.get("plan_title") or "").strip()
        if not plan_title:
            # Fallback retrocompatible: derivar un pseudo-título desde query_prefix
            if prefix:
                words = prefix.split()
                plan_title = " ".join(words[:5])
            else:
                plan_title = "Interacción del Usuario"
        status = (row.get("status") or "UNKNOWN").upper()
        wid = (row.get("worker_id") or "").strip()
        try:
            dur_ms = int(row.get("duration_ms") or 0)
        except (TypeError, ValueError):
            dur_ms = 0
        dur_s = f"{dur_ms / 1000:.1f}s"
        # Formato: número. [subagente] Título del plan · ⏱️ duración
        worker_part = f"[{wid}] " if wid else ""
        title_part = plan_title if plan_title else ""
        lines.append(f"{i}. {worker_part}{title_part} · ⏱️ {dur_s}")

    success_rows = [r for r in filtered if isinstance(r, dict) and (r.get("status") or "").upper() == "SUCCESS"]
    def _dur(r):
        try:
            return int(r.get("duration_ms") or 0)
        except (TypeError, ValueError):
            return 0
    avg_ms = sum(_dur(r) for r in success_rows) / len(success_rows) if success_rows else 0
    try:
        r24 = db.query(
            f"""
            SELECT COUNT(*) as cnt FROM {_TASK_AUDIT_TABLE}
            WHERE tenant_id = '{tenant_s}' AND status = 'FAILED'
            AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            """
        )
        rows24 = json.loads(r24) if isinstance(r24, str) else (r24 or [])
        failed_24h = rows24[0].get("cnt", 0) if rows24 else 0
    except Exception:
        failed_24h = 0
    lines.append(f"— avg {avg_ms/1000:.1f}s · fallidas 24h: {failed_24h}")

    return "\n".join(lines)
