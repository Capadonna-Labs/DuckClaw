"""
Índice de conversaciones admin UI.

Fuente de verdad: DuckDB (``admin_conversations`` / ``admin_conversation_messages``).
Redis / LiteSessionStore: caché best-effort (TTL / memoria de proceso).
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
import asyncio
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from core.admin_conversations_db import (
    _is_generic_conversation_title,
    _title_from_first_message,
)

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
    # Enriquecido en listado (no se persiste en Redis).
    last_worker_display_name: str = ""
    workers: list[str] = Field(default_factory=list)
    last_message_preview: str = ""
    message_count: int = 0
    origin: str = "admin_ui"
    vault_db_path: str = ""
    preferred_worker_id: str = ""


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


async def _cache_upsert_meta(redis_client: Any, meta: AdminConversationMeta) -> None:
    if redis_client is None or meta is None:
        return
    try:
        ttl = _conv_ttl_sec()
        tid = meta.tenant_id
        sid = meta.session_id
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        await redis_client.set(
            _meta_key(tid, sid),
            json.dumps(meta.model_dump(), ensure_ascii=False),
            ex=ttl,
        )
        await redis_client.zadd(_zset_key(tid), {sid: now_ms})
        await redis_client.expire(_zset_key(tid), ttl)
    except Exception as exc:
        _log.debug("admin_conversations: redis cache upsert skip: %s", exc)


async def _redis_get_meta(
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


async def _hydrate_db_from_redis_meta(
    redis_client: Any,
    meta: AdminConversationMeta,
) -> AdminConversationMeta:
    """Copy Redis-only conversation into DuckDB once; return DuckDB row if written."""
    try:
        from core.admin_conversations_db import db_get_conversation_meta, db_save_messages, db_upsert_conversation_meta
        from core.chat_history import redis_load_chat_history

        existing = db_get_conversation_meta(meta.tenant_id, meta.session_id)
        if existing is not None:
            return existing
        written = db_upsert_conversation_meta(
            tenant_id=meta.tenant_id,
            session_id=meta.session_id,
            actor=meta.actor,
            section=meta.section,
            last_worker_id=meta.last_worker_id,
            preferred_worker_id=meta.preferred_worker_id,
            workers=meta.workers,
            message_count=meta.message_count,
            title=meta.title,
            vault_db_path=meta.vault_db_path,
            origin=meta.origin,
            assistant_message=meta.last_message_preview,
        )
        msgs = await redis_load_chat_history(redis_client, meta.tenant_id, meta.session_id)
        if msgs:
            db_save_messages(meta.tenant_id, meta.session_id, msgs)
        return written or meta
    except Exception as exc:
        _log.debug("admin_conversations: hydrate duckdb skip: %s", exc)
        return meta


def admin_conversation_tenant_candidates(primary_tenant_id: str) -> list[str]:
    """Perfil nuevo + conversaciones indexadas bajo ``default`` antes del RBAC por tenant."""
    tid = (primary_tenant_id or "default").strip() or "default"
    if tid == "default":
        return [tid]
    return [tid, "default"]


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


def new_admin_conversation_session_id() -> str:
    return f"{_ADMIN_CONV_PREFIX}{uuid.uuid4().hex}"


async def get_conversation_meta(
    redis_client: Any,
    tenant_id: str,
    session_id: str,
) -> AdminConversationMeta | None:
    from core.admin_conversations_db import db_get_conversation_meta

    tid = (tenant_id or "default").strip() or "default"
    sid = (session_id or "").strip()
    if not sid:
        return None
    redis_meta = await _redis_get_meta(redis_client, tid, sid)
    if redis_meta is not None:
        # Any Redis hit: skip hub. Generic-title DuckDB repair fought db-writer
        # RW lock on every playground poll (get meta log spam).
        return redis_meta
    db_meta = db_get_conversation_meta(tid, sid)
    if db_meta is not None:
        await _cache_upsert_meta(redis_client, db_meta)
        return db_meta
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
    if not should_index_admin_conversation(session_id):
        return None
    from core.admin_conversations_db import db_upsert_conversation_meta

    tid = (tenant_id or "default").strip() or "default"
    sid = (session_id or "").strip()
    if not sid:
        return None
    existing = await get_conversation_meta(redis_client, tid, sid)
    workers = list(existing.workers) if existing else []
    lw = (last_worker_id or "").strip()
    if lw and lw not in workers:
        workers.append(lw)
    preferred = existing.preferred_worker_id if existing else ""
    vault = existing.vault_db_path if existing else ""
    origin = existing.origin if existing else "admin_ui"

    meta = db_upsert_conversation_meta(
        tenant_id=tid,
        session_id=sid,
        actor=actor,
        section=section,
        last_worker_id=lw,
        preferred_worker_id=preferred,
        workers=workers,
        user_message=user_message,
        assistant_message=assistant_message,
        message_count=message_count,
        title=title,
        vault_db_path=vault,
        origin=origin,
        existing=existing,
    )
    if meta is None:
        # Fallback in-memory shape when DuckDB unavailable (tests / misconfig).
        now = _now_iso()
        sec = derive_section_from_session_id(sid, origin_section=section)
        preview = _preview_text((assistant_message or user_message or "").strip())
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
            elif _is_generic_conversation_title(meta.title):
                auto_title = _title_from_first_message(user_message)
                if auto_title:
                    meta.title = auto_title
        else:
            auto_title = _title_from_first_message(user_message) or _title_from_first_message(
                assistant_message
            )
            if not auto_title:
                auto_title = f"Conversación {now[:10]}"
            explicit = (title or "").strip()
            if explicit and not _is_generic_conversation_title(explicit):
                resolved_title = explicit
            elif _title_from_first_message(user_message):
                resolved_title = _title_from_first_message(user_message)
            else:
                resolved_title = explicit or auto_title
            meta = AdminConversationMeta(
                session_id=sid,
                tenant_id=tid,
                title=resolved_title,
                created_at=now,
                updated_at=now,
                actor=(actor or "").strip(),
                section=sec,
                last_worker_id=lw,
                workers=workers,
                last_message_preview=preview,
                message_count=message_count
                if message_count is not None
                else (2 if user_message and assistant_message else 0),
                origin="admin_ui",
            )
    if (
        meta is not None
        and not (title and str(title).strip())
        and existing is not None
        and not _is_generic_conversation_title(existing.title)
    ):
        meta = meta.model_copy(update={"title": existing.title})
    await _cache_upsert_meta(redis_client, meta)
    return meta


async def resolve_conversation_view(
    redis_client: Any,
    primary_tenant_id: str,
    session_id: str,
) -> tuple[str, AdminConversationMeta | None, list[dict[str, Any]]]:
    """Meta + historial: DuckDB primero; Redis fallback + hydrate."""
    from core.admin_conversations_db import db_load_messages
    from core.chat_history import redis_load_chat_history, redis_save_chat_history

    sid = (session_id or "").strip()
    if not sid:
        return (primary_tenant_id or "default").strip() or "default", None, []
    best_meta: AdminConversationMeta | None = None
    best_messages: list[dict[str, Any]] = []
    resolved_tid = (primary_tenant_id or "default").strip() or "default"
    for try_tid in admin_conversation_tenant_candidates(resolved_tid):
        meta = await get_conversation_meta(redis_client, try_tid, sid)
        redis_messages = await redis_load_chat_history(redis_client, try_tid, sid)
        # Redis hit: skip hub RO. Poll + db_load vs db-writer RW = lock spam.
        # Don't db_save on this path (empty db_messages would enqueue a full rewrite).
        if redis_messages:
            messages = redis_messages
        else:
            messages = db_load_messages(try_tid, sid)
        try:
            from duckclaw.graphs.conversation_traces import reconstruct_chat_messages_from_traces

            # Scanning traces.jsonl walks the whole traces tree; only worth it when
            # DuckDB and Redis both came up empty for this session.
            need_traces = not messages
            traced: list[dict[str, str]] = []
            if need_traces:
                traced = await asyncio.to_thread(reconstruct_chat_messages_from_traces, sid)
        except Exception:
            traced = []
        if traced and len(traced) > len(messages):
            messages = traced
            try:
                from core.admin_conversations_db import db_save_messages

                db_save_messages(try_tid, sid, messages)
            except Exception:
                pass
            if redis_client is not None:
                try:
                    await redis_save_chat_history(redis_client, try_tid, sid, messages)
                except Exception:
                    pass
        # Sin meta conocido no se puede refrescar el contador sin inventar un título:
        # el upsert trataría el hilo como nuevo y lo renombraría con el último mensaje.
        if messages and meta is not None and int(meta.message_count or 0) < len(messages):
            last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
            last_asst = next((m["content"] for m in reversed(messages) if m.get("role") == "assistant"), "")
            keep_title = (
                meta.title
                if meta.title and not _is_generic_conversation_title(meta.title)
                else None
            )
            try:
                hydrated_meta = await upsert_conversation_meta(
                    redis_client,
                    tenant_id=try_tid,
                    session_id=sid,
                    actor=meta.actor,
                    last_worker_id=meta.last_worker_id,
                    user_message=last_user,
                    assistant_message=last_asst,
                    message_count=len(messages),
                    title=keep_title,
                )
                if hydrated_meta is not None:
                    meta = hydrated_meta
            except Exception:
                pass
        if meta is None and not messages:
            continue
        if len(messages) > len(redis_messages) and redis_client is not None:
            try:
                await redis_save_chat_history(redis_client, try_tid, sid, messages)
            except Exception:
                pass
        resolved_tid = try_tid
        best_meta = meta
        best_messages = messages
        break
    return resolved_tid, best_meta, best_messages


async def list_conversations_merged(
    redis_client: Any,
    primary_tenant_id: str,
    *,
    section: str | None = None,
    worker: str | None = None,
    actor: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AdminConversationMeta], int]:
    """Lista uniendo tenant del perfil y ``default`` (sin duplicar session_id)."""
    seen: dict[str, AdminConversationMeta] = {}
    for try_tid in admin_conversation_tenant_candidates(primary_tenant_id):
        items, _ = await list_conversations(
            redis_client,
            try_tid,
            section=section,
            worker=worker,
            actor=actor,
            q=q,
            limit=200,
            offset=0,
        )
        for meta in items:
            prev = seen.get(meta.session_id)
            if prev is None or (meta.updated_at or "") > (prev.updated_at or ""):
                seen[meta.session_id] = meta
    merged = sorted(seen.values(), key=lambda m: m.updated_at or "", reverse=True)
    total = len(merged)
    page = merged[offset : offset + limit]
    return page, total


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
    from core.admin_conversations_db import db_list_conversations

    tid = (tenant_id or "default").strip() or "default"
    db_items, db_total = db_list_conversations(
        tid,
        section=section,
        worker=worker,
        actor=actor,
        q=q,
        limit=200,
        offset=0,
    )
    seen: dict[str, AdminConversationMeta] = {m.session_id: m for m in db_items}

    # Merge Redis-only entries and hydrate into DuckDB.
    if redis_client is not None:
        try:
            try:
                session_rows = await redis_client.zrevrange(_zset_key(tid), 0, -1, withscores=True)
            except TypeError:
                ids = await redis_client.zrevrange(_zset_key(tid), 0, -1)
                session_rows = [(i, 0) for i in (ids or [])]
        except Exception:
            session_rows = []
        for row in session_rows or []:
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                sid, score = row[0], row[1]
            else:
                sid, score = row, 0
            sid_s = sid.decode("utf-8") if isinstance(sid, bytes) else str(sid)
            if sid_s in seen:
                continue
            redis_meta = await _redis_get_meta(redis_client, tid, sid_s)
            if redis_meta is not None:
                hydrated = await _hydrate_db_from_redis_meta(redis_client, redis_meta)
                seen[sid_s] = hydrated

    items = list(seen.values())
    sec_f = (section or "").strip().lower()
    worker_f = (worker or "").strip()
    actor_f = (actor or "").strip().lower()
    q_f = (q or "").strip().lower()
    filtered: list[AdminConversationMeta] = []
    for meta in items:
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
        filtered.append(meta)
    filtered.sort(key=lambda m: m.updated_at or "", reverse=True)
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    return filtered[offset : offset + limit], len(filtered)


async def patch_conversation_title(
    redis_client: Any,
    tenant_id: str,
    session_id: str,
    title: str,
) -> AdminConversationMeta | None:
    from core.admin_conversations_db import db_patch_conversation_title

    sid = (session_id or "").strip()
    for try_tid in admin_conversation_tenant_candidates(tenant_id):
        meta = await get_conversation_meta(redis_client, try_tid, sid)
        if meta is None:
            continue
        wanted = (title or "").strip() or meta.title
        patched = db_patch_conversation_title(meta.tenant_id, sid, wanted)
        if patched is None:
            patched = meta.model_copy(update={"title": wanted, "updated_at": _now_iso()})
        elif wanted and patched.title != wanted:
            patched = patched.model_copy(update={"title": wanted, "updated_at": _now_iso()})
        await _cache_upsert_meta(redis_client, patched)
        return patched
    return None


async def patch_conversation_vault(
    redis_client: Any,
    tenant_id: str,
    session_id: str,
    vault_db_path: str | None,
) -> AdminConversationMeta | None:
    """Persiste bóveda DuckDB por conversación (admin UI). Vacío = quitar override."""
    from core.admin_conversations_db import db_patch_conversation_vault

    sid = (session_id or "").strip()
    for try_tid in admin_conversation_tenant_candidates(tenant_id):
        meta = await get_conversation_meta(redis_client, try_tid, sid)
        if meta is None:
            continue
        patched = db_patch_conversation_vault(meta.tenant_id, sid, vault_db_path)
        if patched is None:
            meta.vault_db_path = (vault_db_path or "").strip()
            meta.updated_at = _now_iso()
            patched = meta
        await _cache_upsert_meta(redis_client, patched)
        return patched
    return None


async def patch_conversation_worker(
    redis_client: Any,
    tenant_id: str,
    session_id: str,
    worker_id: str | None,
) -> AdminConversationMeta | None:
    """Persiste worker preferido por conversación (admin UI). Vacío = quitar override."""
    from core.admin_conversations_db import db_patch_conversation_worker

    sid = (session_id or "").strip()
    for try_tid in admin_conversation_tenant_candidates(tenant_id):
        meta = await get_conversation_meta(redis_client, try_tid, sid)
        if meta is None:
            continue
        patched = db_patch_conversation_worker(meta.tenant_id, sid, worker_id)
        if patched is None:
            wid = (worker_id or "").strip()
            meta.preferred_worker_id = wid
            if wid and wid not in meta.workers:
                meta.workers = [*meta.workers, wid]
            meta.updated_at = _now_iso()
            patched = meta
        await _cache_upsert_meta(redis_client, patched)
        return patched
    return None


async def delete_conversation(
    redis_client: Any,
    tenant_id: str,
    session_id: str,
) -> bool:
    from core.admin_conversations_db import db_delete_conversation

    tid = (tenant_id or "default").strip() or "default"
    sid = (session_id or "").strip()
    if not sid:
        return False
    db_ok = db_delete_conversation(tid, sid)
    redis_ok = False
    if redis_client is not None:
        try:
            from core.chat_history import history_redis_key

            await redis_client.delete(_meta_key(tid, sid))
            await redis_client.zrem(_zset_key(tid), sid)
            await redis_client.delete(history_redis_key(tid, sid))
            redis_ok = True
        except Exception as exc:
            _log.warning("admin_conversations: delete redis %s: %s", sid, exc)
    return db_ok or redis_ok


async def delete_conversation_merged(
    redis_client: Any,
    primary_tenant_id: str,
    session_id: str,
) -> str | None:
    """Elimina una conversación desde el mismo espacio lógico que usa el listado.

    Durante la migración RBAC hubo conversaciones indexadas bajo ``default``. La UI
    lista tenant actual + default; borrar debe resolver el tenant real antes de
    limpiar metadatos e historial.
    """
    from core.admin_conversations_db import db_load_messages

    sid = (session_id or "").strip()
    if not sid:
        return None
    for tid in admin_conversation_tenant_candidates(primary_tenant_id):
        meta = await get_conversation_meta(redis_client, tid, sid)
        if meta is None:
            from core.chat_history import redis_load_chat_history

            messages = db_load_messages(tid, sid) or await redis_load_chat_history(
                redis_client, tid, sid
            )
            if not messages:
                continue
        if await delete_conversation(redis_client, tid, sid):
            return tid
    return None


async def reindex_admin_conversations(
    redis_client: Any,
    tenant_id: str,
) -> dict[str, int]:
    """Registra en DuckDB (+ caché Redis) sesiones admin con historial Redis existente."""
    if redis_client is None:
        return {"indexed": 0, "scanned": 0}
    tid = (tenant_id or "default").strip() or "default"
    pattern = f"{_HIST_PREFIX}{tid}:*"
    indexed = 0
    scanned = 0
    try:
        from core.admin_conversations_db import db_save_messages
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
                db_save_messages(tid, sid, msgs)
                indexed += 1
            if cursor == 0:
                break
    except Exception as exc:
        _log.warning("admin_conversations: reindex %s: %s", tid, exc)
    return {"indexed": indexed, "scanned": scanned}


def enrich_conversations_worker_display_names(
    items: list[AdminConversationMeta],
    *,
    tenant_id: str,
) -> list[AdminConversationMeta]:
    """Resuelve ``last_worker_display_name`` desde el catálogo DB (batch)."""
    if not items:
        return items
    worker_ids = sorted(
        {
            (m.last_worker_id or "").strip()
            for m in items
            if (m.last_worker_id or "").strip()
        }
    )
    if not worker_ids:
        return items

    labels: dict[str, str] = {}
    tid = (tenant_id or "default").strip() or "default"
    try:
        from core.admin_identity import open_gateway_db
        from duckclaw.admin_worker_catalog import get_worker_by_tenant_worker_id

        with open_gateway_db(read_only=True) as db:
            for wid in worker_ids:
                row = get_worker_by_tenant_worker_id(db, tenant_id=tid, worker_id=wid)
                if not row and tid != "default":
                    row = get_worker_by_tenant_worker_id(db, tenant_id="default", worker_id=wid)
                name = str((row or {}).get("display_name") or "").strip()
                if name and name.lower() != wid.lower():
                    labels[wid] = name
    except Exception as exc:
        _log.warning("admin_conversations: enrich display names: %s", exc)
        return items

    if not labels:
        return items

    enriched: list[AdminConversationMeta] = []
    for meta in items:
        wid = (meta.last_worker_id or "").strip()
        label = labels.get(wid, "")
        if label and meta.last_worker_display_name != label:
            enriched.append(meta.model_copy(update={"last_worker_display_name": label}))
        else:
            enriched.append(meta)
    return enriched
