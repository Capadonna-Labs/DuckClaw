"""
Índice de conversaciones admin UI en Redis (metadatos + listado).

Complementa ``chat_history.py`` (mensajes). Solo sesiones admin UI o ``admin-conv-*``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)

_CONV_ZSET_PREFIX = "duckclaw:admin:conv:z:"
_CONV_META_PREFIX = "duckclaw:admin:conv:meta:"
_HIST_PREFIX = "duckclaw:gateway:chat_hist:"
_ADMIN_CONV_PREFIX = "admin-conv-"
_PREVIEW_MAX = 120
_TITLE_MAX = 80


class AdminConversationMeta(BaseModel):
    session_id: str
    tenant_id: str
    title: str = ""
    created_at: str = ""
    updated_at: str = ""
    actor: str = ""
    section: str = "other"
    last_worker_id: str = ""
    workers: list[str] = Field(default_factory=list)
    last_message_preview: str = ""
    message_count: int = 0
    origin: str = "admin_ui"


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _conv_ttl_sec() -> int:
    raw = (os.environ.get("DUCKCLAW_ADMIN_CONV_INDEX_TTL_SEC") or "").strip()
    if raw:
        try:
            return max(60, int(raw))
        except ValueError:
            pass
    return int(os.environ.get("DUCKCLAW_CHAT_HISTORY_TTL_SEC", "604800"))


def _zset_key(tenant_id: str) -> str:
    tid = (tenant_id or "default").strip() or "default"
    return f"{_CONV_ZSET_PREFIX}{tid}"


def _meta_key(tenant_id: str, session_id: str) -> str:
    tid = (tenant_id or "default").strip() or "default"
    sid = (session_id or "").strip()
    return f"{_CONV_META_PREFIX}{tid}:{sid}"


def should_index_admin_conversation(session_id: str) -> bool:
    sid = (session_id or "").strip()
    if not sid:
        return False
    if sid.startswith(_ADMIN_CONV_PREFIX):
        return True
    try:
        from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

        return bool(is_admin_ui_chat_session(sid))
    except Exception:
        return sid.startswith("admin-")


def derive_section_from_session_id(session_id: str, *, origin_section: str | None = None) -> str:
    if (origin_section or "").strip():
        return (origin_section or "").strip().lower()
    sid = (session_id or "").strip()
    if sid == "admin-playground":
        return "playground"
    if sid.startswith("admin-section-"):
        slug = sid[len("admin-section-") :]
        if slug in ("", "root"):
            return "root"
        if slug.startswith("kanban"):
            return "kanban"
        if slug.startswith("vnc"):
            return "vnc"
        if slug.startswith("train"):
            return "train"
        return slug.split("-")[0] if slug else "other"
    if sid.startswith(_ADMIN_CONV_PREFIX):
        return ""
    return "other"


def _preview_text(text: str) -> str:
    t = " ".join((text or "").split())
    if len(t) > _PREVIEW_MAX:
        return t[: _PREVIEW_MAX - 1] + "…"
    return t


def _title_from_first_message(text: str) -> str:
    t = " ".join((text or "").split())
    if not t:
        return ""
    if len(t) > _TITLE_MAX:
        return t[: _TITLE_MAX - 1].rstrip() + "…"
    return t


def new_admin_conversation_session_id() -> str:
    return f"{_ADMIN_CONV_PREFIX}{uuid.uuid4().hex}"


async def get_conversation_meta(
    redis_client: Any,
    tenant_id: str,
    session_id: str,
) -> AdminConversationMeta | None:
    if redis_client is None:
        return None
    key = _meta_key(tenant_id, session_id)
    try:
        raw = await redis_client.get(key)
        if not raw:
            return None
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        return AdminConversationMeta.model_validate(data)
    except Exception as exc:
        _log.warning("admin_conversations: get meta %s: %s", key, exc)
        return None


async def upsert_conversation_meta(
    redis_client: Any,
    *,
    tenant_id: str,
    session_id: str,
    actor: str = "",
    section: str | None = None,
    last_worker_id: str = "",
    user_message: str = "",
    assistant_message: str = "",
    message_count: int | None = None,
    title: str | None = None,
) -> AdminConversationMeta | None:
    if redis_client is None or not should_index_admin_conversation(session_id):
        return None
    tid = (tenant_id or "default").strip() or "default"
    sid = (session_id or "").strip()
    if not sid:
        return None
    now = _now_iso()
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    ttl = _conv_ttl_sec()
    existing = await get_conversation_meta(redis_client, tid, sid)
    sec = derive_section_from_session_id(sid, origin_section=section)
    workers = list(existing.workers) if existing else []
    lw = (last_worker_id or "").strip()
    if lw and lw not in workers:
        workers.append(lw)
    preview_src = (assistant_message or user_message or "").strip()
    preview = _preview_text(preview_src)
    if existing:
        meta = existing.model_copy(
            update={
                "updated_at": now,
                "actor": (actor or existing.actor or "").strip() or existing.actor,
                "section": (sec or existing.section) if sec else existing.section,
                "last_worker_id": lw or existing.last_worker_id,
                "workers": workers,
                "last_message_preview": preview or existing.last_message_preview,
                "message_count": message_count
                if message_count is not None
                else existing.message_count + (1 if user_message and assistant_message else 0),
            }
        )
        if title and title.strip():
            meta.title = title.strip()
    else:
        auto_title = _title_from_first_message(user_message) or _title_from_first_message(
            assistant_message
        )
        if not auto_title:
            auto_title = f"Conversación {now[:10]}"
        meta = AdminConversationMeta(
            session_id=sid,
            tenant_id=tid,
            title=(title or auto_title).strip(),
            created_at=now,
            updated_at=now,
            actor=(actor or "").strip(),
            section=sec,
            last_worker_id=lw,
            workers=workers,
            last_message_preview=preview,
            message_count=message_count if message_count is not None else (2 if user_message and assistant_message else 0),
            origin="admin_ui",
        )
    meta_key = _meta_key(tid, sid)
    zkey = _zset_key(tid)
    try:
        payload = meta.model_dump()
        await redis_client.set(meta_key, json.dumps(payload, ensure_ascii=False), ex=ttl)
        await redis_client.zadd(zkey, {sid: now_ms})
        await redis_client.expire(zkey, ttl)
        return meta
    except Exception as exc:
        _log.warning("admin_conversations: upsert %s: %s", meta_key, exc)
        return None


async def list_conversations(
    redis_client: Any,
    tenant_id: str,
    *,
    section: str | None = None,
    worker: str | None = None,
    actor: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AdminConversationMeta], int]:
    if redis_client is None:
        return [], 0
    tid = (tenant_id or "default").strip() or "default"
    zkey = _zset_key(tid)
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    try:
        session_ids = await redis_client.zrevrange(zkey, 0, -1)
    except Exception as exc:
        _log.warning("admin_conversations: zrevrange %s: %s", zkey, exc)
        return [], 0
    if not session_ids:
        return [], 0
    decoded: list[str] = []
    for sid in session_ids:
        if isinstance(sid, bytes):
            decoded.append(sid.decode("utf-8", errors="replace"))
        else:
            decoded.append(str(sid))
    items: list[AdminConversationMeta] = []
    sec_f = (section or "").strip().lower()
    worker_f = (worker or "").strip()
    actor_f = (actor or "").strip().lower()
    q_f = (q or "").strip().lower()
    for sid in decoded:
        meta = await get_conversation_meta(redis_client, tid, sid)
        if meta is None:
            continue
        if sec_f and meta.section.lower() != sec_f:
            continue
        if worker_f:
            if meta.last_worker_id != worker_f and worker_f not in meta.workers:
                continue
        if actor_f and actor_f not in (meta.actor or "").lower():
            continue
        if q_f:
            blob = f"{meta.title} {meta.last_message_preview}".lower()
            if q_f not in blob:
                continue
        items.append(meta)
    total = len(items)
    page = items[offset : offset + limit]
    return page, total


async def patch_conversation_title(
    redis_client: Any,
    tenant_id: str,
    session_id: str,
    title: str,
) -> AdminConversationMeta | None:
    meta = await get_conversation_meta(redis_client, tenant_id, session_id)
    if meta is None:
        return None
    meta.title = (title or "").strip() or meta.title
    meta.updated_at = _now_iso()
    ttl = _conv_ttl_sec()
    try:
        await redis_client.set(
            _meta_key(tenant_id, session_id),
            json.dumps(meta.model_dump(), ensure_ascii=False),
            ex=ttl,
        )
        return meta
    except Exception as exc:
        _log.warning("admin_conversations: patch %s: %s", session_id, exc)
        return None


async def delete_conversation(
    redis_client: Any,
    tenant_id: str,
    session_id: str,
) -> bool:
    if redis_client is None:
        return False
    tid = (tenant_id or "default").strip() or "default"
    sid = (session_id or "").strip()
    if not sid:
        return False
    try:
        from core.chat_history import history_redis_key

        await redis_client.delete(_meta_key(tid, sid))
        await redis_client.zrem(_zset_key(tid), sid)
        await redis_client.delete(history_redis_key(tid, sid))
        return True
    except Exception as exc:
        _log.warning("admin_conversations: delete %s: %s", sid, exc)
        return False


async def reindex_admin_conversations(
    redis_client: Any,
    tenant_id: str,
) -> dict[str, int]:
    """Registra en el índice sesiones admin con historial Redis existente."""
    if redis_client is None:
        return {"indexed": 0, "scanned": 0}
    tid = (tenant_id or "default").strip() or "default"
    pattern = f"{_HIST_PREFIX}{tid}:*"
    indexed = 0
    scanned = 0
    try:
        from core.chat_history import redis_load_chat_history

        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor=cursor, match=pattern, count=100)
            for key in keys:
                key_s = key.decode("utf-8") if isinstance(key, bytes) else str(key)
                scanned += 1
                m = re.match(rf"^{re.escape(_HIST_PREFIX)}{re.escape(tid)}:(.+)$", key_s)
                if not m:
                    continue
                sid = m.group(1)
                if not should_index_admin_conversation(sid):
                    continue
                msgs = await redis_load_chat_history(redis_client, tid, sid)
                if not msgs:
                    continue
                last_user = ""
                last_asst = ""
                workers: list[str] = []
                for item in msgs:
                    role = item.get("role")
                    content = (item.get("content") or "").strip()
                    if role == "user":
                        last_user = content
                    elif role == "assistant":
                        last_asst = content
                await upsert_conversation_meta(
                    redis_client,
                    tenant_id=tid,
                    session_id=sid,
                    user_message=last_user,
                    assistant_message=last_asst,
                    message_count=len(msgs),
                )
                indexed += 1
            if cursor == 0:
                break
    except Exception as exc:
        _log.warning("admin_conversations: reindex %s: %s", tid, exc)
    return {"indexed": indexed, "scanned": scanned}
