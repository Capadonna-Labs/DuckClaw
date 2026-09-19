"""Sugerencias breves de continuación para el input del chat (post-turno, no bloquea el SSE)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from core.background_tasks import spawn_background
from routers.admin_domains.admin_common import actor_from_header, problem, require_admin_key

_log = logging.getLogger("duckclaw.gateway.chat_suggestions")

_SUGGESTIONS_CACHE_PREFIX = "duckclaw:chat_suggestions:"
_SUGGESTIONS_CACHE_TTL = 600  # 10 min — solo tiene que sobrevivir hasta que el reloj responda.

router = APIRouter(tags=["admin-chat-suggestions"])


class ChatSuggestionsBody(BaseModel):
    chat_id: str = Field(..., max_length=128)
    tenant_id: str = Field(default="default", max_length=64)
    last_user_message: str = Field(default="", max_length=8000)
    last_assistant_message: str = Field(default="", max_length=16000)
    vault_db_path: str = Field(default="", max_length=1024)


class ChatSuggestionsAutoBody(BaseModel):
    chat_id: str = Field(..., max_length=128)
    tenant_id: str = Field(default="default", max_length=64)
    enabled: bool = False
    vault_db_path: str = Field(default="", max_length=1024)


class ChatSuggestionSelectBody(BaseModel):
    chat_id: str = Field(..., max_length=128)
    tenant_id: str = Field(default="default", max_length=64)
    index: int = Field(..., ge=0, le=2)


async def _cache_suggestions(redis_client: Any, chat_id: str, tenant_id: str, suggestions: list[str]) -> None:
    if redis_client is None or not suggestions:
        return
    try:
        await redis_client.set(
            f"{_SUGGESTIONS_CACHE_PREFIX}{chat_id}",
            json.dumps({"tenant_id": tenant_id, "suggestions": suggestions}),
            ex=_SUGGESTIONS_CACHE_TTL,
        )
    except Exception:
        _log.debug("suggestions cache write skipped", exc_info=True)


async def _read_cached_suggestions(redis_client: Any, chat_id: str) -> dict[str, Any] | None:
    if redis_client is None:
        return None
    try:
        raw = await redis_client.get(f"{_SUGGESTIONS_CACHE_PREFIX}{chat_id}")
    except Exception:
        return None
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


async def _notify_suggestions_ready(chat_id: str, suggestions: list[str]) -> None:
    """Push best-effort listando las opciones numeradas — permite elegir desde el reloj."""
    if not suggestions:
        return
    try:
        from duckclaw.gateway_db import get_gateway_db_path
        from duckclaw.web_push import list_web_push_subscriptions, send_web_push_notifications

        db_path = str(get_gateway_db_path())
        subs = await asyncio.to_thread(list_web_push_subscriptions, db_path)
        if not subs:
            return
        body = "\n".join(f"{i + 1}) {text}" for i, text in enumerate(suggestions[:3]))
        await asyncio.to_thread(
            send_web_push_notifications,
            subs,
            title="DuckClaw · elegí una sugerencia",
            body=body,
            url="/playground",
            tag=f"duckclaw-suggestions-{chat_id}",
        )
    except Exception:
        _log.debug("suggestions push notification skipped", exc_info=True)


def _resolve_state_db_path(vault_db_path: str = "") -> str:
    from duckclaw.gateway_db import get_gateway_db_path, resolve_env_duckdb_path

    vault = resolve_env_duckdb_path((vault_db_path or "").strip())
    if vault and os.path.isfile(vault):
        return vault
    gw = resolve_env_duckdb_path((get_gateway_db_path() or "").strip())
    return gw if gw and os.path.isfile(gw) else ""


def _read_suggestions_auto(chat_id: str, vault_db_path: str = "") -> bool | None:
    from duckclaw import DuckClaw
    from duckclaw.commands.suggestions_auto import suggestions_auto_enabled

    path = _resolve_state_db_path(vault_db_path)
    if not path:
        return None
    db = DuckClaw(path, read_only=True)
    try:
        return suggestions_auto_enabled(db, chat_id)
    finally:
        try:
            db.close()
        except Exception:
            pass


@router.post("/chat/suggestions", dependencies=[Depends(require_admin_key)])
async def post_chat_suggestions(body: ChatSuggestionsBody, request: Request) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.commands.chat_suggestions import generate_followup_suggestions
    from duckclaw.gateway_db import get_gateway_db_path

    auto = _read_suggestions_auto(body.chat_id, body.vault_db_path)
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        return {
            "suggestions": [],
            "recommended_index": 0,
            "suggestions_auto_enabled": auto,
        }

    def _load_suggestions():
        db = DuckClaw(gw, read_only=True)
        try:
            return generate_followup_suggestions(
                db,
                body.chat_id,
                tenant_id=body.tenant_id,
                last_user_text=body.last_user_message,
                last_assistant_text=body.last_assistant_message,
            )
        finally:
            db.close()

    payload = await asyncio.to_thread(_load_suggestions)
    if isinstance(payload, dict):
        suggestions = payload.get("suggestions") if isinstance(payload.get("suggestions"), list) else []
        try:
            recommended_index = int(payload.get("recommended_index") or 0)
        except (TypeError, ValueError):
            recommended_index = 0
    else:
        # Legacy list return (tests / older builds).
        suggestions = list(payload) if isinstance(payload, list) else []
        recommended_index = 0
    if recommended_index < 0 or recommended_index >= len(suggestions):
        recommended_index = 0
    if suggestions:
        redis_client = getattr(request.app.state, "redis", None)
        spawn_background(_cache_suggestions(redis_client, body.chat_id, body.tenant_id, suggestions))
        spawn_background(_notify_suggestions_ready(body.chat_id, suggestions))
    return {
        "suggestions": suggestions,
        "recommended_index": recommended_index,
        "suggestions_auto_enabled": auto,
    }


@router.post("/chat/suggestions/auto", dependencies=[Depends(require_admin_key)])
async def post_chat_suggestions_auto(body: ChatSuggestionsAutoBody) -> dict[str, Any]:
    """UI toggle: persist Auto preference for this chat (clears agent suppress when enabling)."""
    from duckclaw import DuckClaw
    from duckclaw.commands.suggestions_auto import set_suggestions_auto_enabled

    path = _resolve_state_db_path(body.vault_db_path)
    if not path:
        return {"ok": False, "error": "vault_unavailable", "suggestions_auto_enabled": None}
    # read_only → typed DB-Writer enqueue (same as loop tools).
    db = DuckClaw(path, read_only=True)
    try:
        ok, err = set_suggestions_auto_enabled(
            db,
            body.chat_id,
            bool(body.enabled),
            tenant_id=body.tenant_id,
        )
    finally:
        try:
            db.close()
        except Exception:
            pass
    if not ok:
        return {
            "ok": False,
            "error": err or "persist_failed",
            "suggestions_auto_enabled": None,
        }
    return {"ok": True, "suggestions_auto_enabled": bool(body.enabled)}


@router.post("/chat/suggestions/select", dependencies=[Depends(require_admin_key)])
async def post_chat_suggestions_select(
    body: ChatSuggestionSelectBody,
    request: Request,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    """Elige una de las últimas 3 sugerencias cacheadas y la manda como turno nuevo.

    Pensado para dispararse desde afuera del navegador (reloj vía Tasker) — solo
    necesita chat_id + índice, resuelve el resto (worker, sugerencias) del lado
    del servidor.
    """
    from core.admin_conversations import get_conversation_meta
    from routers.admin_domains.playground.chat_turn import (
        invoke_playground_chat_sync,
        prepare_playground_chat_turn,
    )

    redis_client = getattr(request.app.state, "redis", None)
    cached = await _read_cached_suggestions(redis_client, body.chat_id)
    suggestions = (cached or {}).get("suggestions") or []
    if not suggestions:
        raise problem(404, "Sin sugerencias recientes para este chat", body.chat_id)
    if body.index >= len(suggestions):
        raise problem(400, "Índice fuera de rango", f"index={body.index} count={len(suggestions)}")
    message = str(suggestions[body.index] or "").strip()
    if not message:
        raise problem(400, "Sugerencia vacía", str(body.index))

    tenant_id = str((cached or {}).get("tenant_id") or body.tenant_id or "default").strip() or "default"
    meta = await get_conversation_meta(redis_client, tenant_id, body.chat_id)
    worker_id = (getattr(meta, "last_worker_id", "") or "default").strip() or "default"

    from routers.admin_domains.playground.schemas import PlaygroundChatBody

    chat_body = PlaygroundChatBody(
        worker_id=worker_id,
        message=message,
        chat_id=body.chat_id,
        tenant_id=tenant_id,
    )
    prepared = await prepare_playground_chat_turn(chat_body, actor=actor, request=request)
    await invoke_playground_chat_sync(prepared, request=request)
    return {"ok": True, "chat_id": body.chat_id, "index": body.index, "message": message}
