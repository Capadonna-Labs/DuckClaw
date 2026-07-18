"""Rutas de historial y CRUD de conversaciones admin playground."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, Query, Request

from routers.admin_domains.admin_common import actor_from_header, problem, require_admin_key
from routers.admin_domains.playground.router import router
from routers.admin_domains.playground.schemas import AdminConversationCreateBody, AdminConversationPatchBody
from routers.admin_domains.playground.tenant_resolution import gateway_effective_tenant_id


@router.get("/chats/history", dependencies=[Depends(require_admin_key)])
async def admin_chat_history(
    request: Request,
    tenant_id: str = Query("default"),
    session_id: str = Query(...),
) -> dict[str, Any]:
    from core.chat_history import redis_load_chat_history

    redis_client = getattr(request.app.state, "redis", None)
    items = await redis_load_chat_history(redis_client, tenant_id, session_id)
    return {"tenant_id": tenant_id, "session_id": session_id, "messages": items}


@router.get("/conversations", dependencies=[Depends(require_admin_key)])
async def admin_list_conversations(
    request: Request,
    tenant_id: str = Query("default"),
    section: str | None = Query(None),
    worker: str | None = Query(None),
    actor: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    from core.admin_conversations import (
        enrich_conversations_worker_display_names,
        list_conversations_merged,
    )

    tid = gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    redis_client = getattr(request.app.state, "redis", None)
    items, total = await list_conversations_merged(
        redis_client,
        tid,
        section=section,
        worker=worker,
        actor=actor,
        q=q,
        limit=limit,
        offset=offset,
    )
    items = enrich_conversations_worker_display_names(items, tenant_id=tid)
    return {
        "tenant_id": tid,
        "conversations": [m.model_dump() for m in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/conversations", dependencies=[Depends(require_admin_key)])
async def admin_create_conversation(
    request: Request,
    body: AdminConversationCreateBody,
    tenant_id: str = Query("default"),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_conversations import (
        AdminConversationMeta,
        derive_section_from_session_id,
        new_admin_conversation_session_id,
        patch_conversation_worker,
        upsert_conversation_meta,
    )

    tid = gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    sid = new_admin_conversation_session_id()
    sec = (body.section or "").strip() or "other"
    redis_client = getattr(request.app.state, "redis", None)
    title = (body.title or "").strip() or f"Conversación {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    init_worker = re.sub(r"[^a-zA-Z0-9_-]", "", (body.worker_id or "").strip())
    meta = await upsert_conversation_meta(
        redis_client,
        tenant_id=tid,
        session_id=sid,
        actor=actor,
        section=sec,
        last_worker_id=init_worker,
        title=title,
        message_count=0,
    )
    if meta is None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        meta = AdminConversationMeta(
            session_id=sid,
            tenant_id=tid,
            title=title,
            created_at=now,
            updated_at=now,
            actor=actor,
            section=derive_section_from_session_id(sid, origin_section=sec),
            last_worker_id=init_worker,
            preferred_worker_id=init_worker,
            workers=[init_worker] if init_worker else [],
            origin="admin_ui",
        )
    elif init_worker:
        patched = await patch_conversation_worker(redis_client, tid, sid, init_worker)
        if patched is not None:
            meta = patched
    return meta.model_dump()


@router.get("/conversations/{session_id}", dependencies=[Depends(require_admin_key)])
async def admin_get_conversation(
    request: Request,
    session_id: str,
    tenant_id: str = Query("default"),
) -> dict[str, Any]:
    from core.admin_conversations import resolve_conversation_view

    tid = gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    sid = (session_id or "").strip()
    if not sid:
        raise problem(400, "session_id vacío", session_id)
    redis_client = getattr(request.app.state, "redis", None)
    resolved_tid, meta, messages = await resolve_conversation_view(redis_client, tid, sid)
    if meta is None and not messages:
        raise problem(404, "Conversación no encontrada", sid)
    out: dict[str, Any] = {
        "tenant_id": resolved_tid,
        "session_id": sid,
        "messages": messages,
    }
    if meta is not None:
        out.update(meta.model_dump())
    return out


@router.patch("/conversations/{session_id}", dependencies=[Depends(require_admin_key)])
async def admin_patch_conversation(
    request: Request,
    session_id: str,
    body: AdminConversationPatchBody,
    tenant_id: str = Query("default"),
) -> dict[str, Any]:
    from core.admin_conversations import patch_conversation_title

    tid = gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    sid = (session_id or "").strip()
    title = (body.title or "").strip()
    if not sid or not title:
        raise problem(400, "session_id y title requeridos", sid)
    redis_client = getattr(request.app.state, "redis", None)
    meta = await patch_conversation_title(redis_client, tid, sid, title)
    if meta is None:
        raise problem(404, "Conversación no encontrada", sid)
    return meta.model_dump()


@router.delete("/conversations/{session_id}", dependencies=[Depends(require_admin_key)])
async def admin_delete_conversation(
    request: Request,
    session_id: str,
    tenant_id: str = Query("default"),
) -> dict[str, Any]:
    from core.admin_conversations import delete_conversation_merged

    tid = gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    sid = (session_id or "").strip()
    if not sid:
        raise problem(400, "session_id vacío", session_id)
    redis_client = getattr(request.app.state, "redis", None)
    deleted_tid = await delete_conversation_merged(redis_client, tid, sid)
    if deleted_tid is None:
        raise problem(404, "Conversación no encontrada", sid)
    return {"ok": True, "hard_deleted": True, "session_id": sid, "tenant_id": deleted_tid}


@router.post("/conversations/reindex", dependencies=[Depends(require_admin_key)])
async def admin_reindex_conversations(
    request: Request,
    tenant_id: str = Query("default"),
) -> dict[str, Any]:
    from core.admin_conversations import reindex_admin_conversations

    tid = gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    redis_client = getattr(request.app.state, "redis", None)
    stats = await reindex_admin_conversations(redis_client, tid)
    return {"tenant_id": tid, **stats}
