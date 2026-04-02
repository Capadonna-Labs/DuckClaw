from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Tuple


_WR_TENANT_PREFIX = "wr_"
_WR_ALLOWED_CLEARANCE = {"admin", "operator", "observer"}


def is_war_room_tenant(tenant_id: str | None) -> bool:
    return str(tenant_id or "").strip().lower().startswith(_WR_TENANT_PREFIX)


def war_room_tenant_for_chat(chat_type: str | None, chat_id: Any, fallback_tenant: str) -> str:
    ctype = str(chat_type or "").strip().lower()
    if ctype not in ("group", "supergroup"):
        return str(fallback_tenant or "default").strip() or "default"
    return f"{_WR_TENANT_PREFIX}{str(chat_id).strip()}"


def ensure_war_room_schema(db: Any) -> None:
    if getattr(db, "_war_room_acl_readonly", False):
        return
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


def _sql_lit(value: Any, max_len: int = 4096) -> str:
    return str(value if value is not None else "").replace("'", "''")[:max_len]


def wr_lookup_member_clearance(db: Any, tenant_id: str, user_id: str) -> str:
    ensure_war_room_schema(db)
    tid = _sql_lit(tenant_id, 256)
    uid = _sql_lit(user_id, 256)
    try:
        raw = db.query(
            "SELECT clearance_level FROM war_room_core.wr_members "
            f"WHERE lower(tenant_id)=lower('{tid}') AND user_id='{uid}' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            return str(rows[0].get("clearance_level") or "").strip().lower()
    except Exception:
        return ""
    return ""


def wr_has_member(db: Any, tenant_id: str, user_id: str) -> bool:
    return bool(wr_lookup_member_clearance(db, tenant_id, user_id))


def wr_members_count(db: Any, tenant_id: str) -> int:
    ensure_war_room_schema(db)
    tid = _sql_lit(tenant_id, 256)
    try:
        raw = db.query(
            "SELECT count(*) AS c FROM war_room_core.wr_members "
            f"WHERE lower(tenant_id)=lower('{tid}')"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            return int(rows[0].get("c") or 0)
    except Exception:
        return 0
    return 0


def wr_upsert_member(
    db: Any,
    *,
    tenant_id: str,
    user_id: str,
    username: str,
    clearance_level: str,
) -> None:
    ensure_war_room_schema(db)
    clr = str(clearance_level or "").strip().lower()
    if clr not in _WR_ALLOWED_CLEARANCE:
        clr = "observer"
    db.execute(
        "INSERT INTO war_room_core.wr_members (tenant_id, user_id, username, clearance_level) "
        f"VALUES ('{_sql_lit(tenant_id, 256)}', '{_sql_lit(user_id, 256)}', "
        f"'{_sql_lit(username or 'Usuario', 128)}', '{_sql_lit(clr, 32)}') "
        "ON CONFLICT (tenant_id, user_id) DO UPDATE SET "
        "username=EXCLUDED.username, clearance_level=EXCLUDED.clearance_level, added_at=now()"
    )


def wr_append_audit(
    db: Any,
    *,
    tenant_id: str,
    sender_id: str,
    target_agent: str | None,
    event_type: str,
    payload: str,
) -> None:
    ensure_war_room_schema(db)
    db.execute(
        "INSERT INTO war_room_core.wr_audit_log (event_id, tenant_id, sender_id, target_agent, event_type, payload) "
        f"VALUES ('{uuid.uuid4()}', '{_sql_lit(tenant_id, 256)}', '{_sql_lit(sender_id, 256)}', "
        f"'{_sql_lit(target_agent or '', 128)}', '{_sql_lit(event_type, 64)}', '{_sql_lit(payload, 8000)}')"
    )


def _utf16_slice(text: str, offset: int, length: int) -> str:
    """Telegram MessageEntity offset/length están en unidades UTF-16 (no índices Python)."""
    t = str(text or "")
    if length <= 0:
        return ""
    try:
        raw = t.encode("utf-16-le")
        return raw[offset * 2 : (offset + length) * 2].decode("utf-16-le")
    except Exception:
        return ""


def parse_mentions(text: str, entities: list[dict[str, Any]] | None = None) -> set[str]:
    out: set[str] = set()
    t = str(text or "")
    for m in re.finditer(r"@([A-Za-z0-9_][A-Za-z0-9_\-]{1,63})", t):
        out.add(m.group(1).lower())
    for ent in entities or []:
        if not isinstance(ent, dict):
            continue
        et = str(ent.get("type") or "").strip().lower()
        if et == "mention":
            off = int(ent.get("offset") or 0)
            ln = int(ent.get("length") or 0)
            frag = _utf16_slice(t, off, ln) if (off or ln) else ""
            if frag.startswith("@"):
                out.add(frag[1:].strip().lower())
        elif et == "text_mention":
            user = ent.get("user")
            if isinstance(user, dict):
                un = str(user.get("username") or "").strip().lstrip("@").lower()
                if un:
                    out.add(un)
                else:
                    frag = _utf16_slice(t, int(ent.get("offset") or 0), int(ent.get("length") or 0))
                    if frag.startswith("@"):
                        out.add(frag[1:].strip().lower())
    return out


def normalize_telegram_bot_username(raw: str | None) -> str:
    """Quita '@' y normaliza a lowercase; coincide con settings.TELEGRAM_BOT_USERNAME."""
    return str(raw or "").strip().lstrip("@").lower()


@dataclass(frozen=True)
class WarRoomMentionGateResult:
    allowed: bool
    """ALLOWED_COMMAND | ALLOWED_MENTION | ALLOWED_VISUAL_CAPTION | ALLOWED_BOOTSTRAP | DROP_NO_MENTION"""

    decision: str


def message_refs_current_telegram_bot(
    text: str,
    entities: list[dict[str, Any]] | None,
    *,
    current_bot_username: str,
) -> bool:
    """
    True si el texto/caption menciona al bot de este gateway (username normalizado) o 'duckclaw'.
    No hardcodea otros bots: solo configuración + alias legacy duckclaw.
    """
    cu = normalize_telegram_bot_username(current_bot_username)
    t = str(text or "")
    mentions = parse_mentions(t, entities)
    if "duckclaw" in mentions:
        return True
    if cu and cu in mentions:
        return True
    if cu and f"@{cu}" in t.lower():
        return True
    return False


def war_room_evaluate_mention_gate(
    *,
    combined_text: str,
    entities: list[dict[str, Any]] | None,
    has_visual_media: bool,
    current_bot_username: str,
    bootstrap_mode: bool,
) -> WarRoomMentionGateResult:
    """
    War Room (grupo/supergrupo → tenant wr_*): fly commands, mención al bot actual en texto o
    en caption de foto, o bootstrap sin miembros aún.
    """
    ct = str(combined_text or "").strip()
    if ct.startswith("/"):
        return WarRoomMentionGateResult(True, "ALLOWED_COMMAND")
    if has_visual_media:
        if message_refs_current_telegram_bot(ct, entities, current_bot_username=current_bot_username):
            return WarRoomMentionGateResult(True, "ALLOWED_VISUAL_CAPTION")
        return WarRoomMentionGateResult(False, "DROP_NO_MENTION")
    if bootstrap_mode:
        return WarRoomMentionGateResult(True, "ALLOWED_BOOTSTRAP")
    if message_refs_current_telegram_bot(ct, entities, current_bot_username=current_bot_username):
        return WarRoomMentionGateResult(True, "ALLOWED_MENTION")
    return WarRoomMentionGateResult(False, "DROP_NO_MENTION")


def is_explicit_wr_invocation(
    text: str,
    *,
    entities: list[dict[str, Any]] | None = None,
    bot_aliases: set[str],
    worker_aliases: set[str],
) -> bool:
    mentions = parse_mentions(text, entities)
    if not mentions:
        return False
    allowed = {x.lower() for x in bot_aliases | worker_aliases if str(x).strip()}
    return bool(mentions.intersection(allowed))


async def hit_rate_limit(
    redis_client: Any,
    *,
    tenant_id: str,
    user_id: str,
    cooldown_seconds: int = 300,
    max_messages: int = 8,
) -> Tuple[bool, bool, int]:
    if redis_client is None:
        return (True, False, 0)
    key = f"wr:rate:{tenant_id}:{user_id}"
    notify_key = f"wr_cooldown_notified:{tenant_id}:{user_id}"
    window = int(max(1, cooldown_seconds))
    limit = int(max(1, max_messages))
    try:
        count = int(await redis_client.incr(key))
        if count == 1:
            await redis_client.expire(key, window)
        ttl = int(await redis_client.ttl(key))
        if ttl <= 0:
            ttl = window

        if count <= limit:
            return (True, False, ttl)

        already_notified = await redis_client.get(notify_key)
        if already_notified:
            return (False, False, ttl)

        await redis_client.set(notify_key, "1", ex=max(1, ttl), nx=True)
        return (False, True, ttl)
    except Exception:
        # Fail-open: no bloquear operación por una caída temporal de Redis.
        return (True, False, 0)
