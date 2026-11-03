"""Worlds: a bot's conversation with its owner, visible and writable from the admin playground.

The conversation is one playground conversation per bot (``admin-conv-<hex>``, so the playground lists it and any admin session can open it). Two directions:

* person -> bot: ``POST /worlds/bots/say`` (admin key) appends the message to the conversation and to the bot's inbox (a Redis list, capped, expiring);
  the runner drains it with ``GET /worlds/bots/inbox`` (runner key) and treats each message as if the owner had said it where the bot lives.
* bot -> person: the runner publishes what was said on either side with ``POST /worlds/bots/transcript`` (runner key).

The transcript is plain dialogue. The planner's own turns (``/worlds/think``) stay in their own chat, which holds the whole sensorium prompt and is not meant to be read.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import actor_from_header, problem, require_admin_key
from routers.admin_domains.worlds import _existing_bot, _profile, require_admin_or_runner_key

router = APIRouter(prefix="/worlds", tags=["admin-worlds"])

_INBOX_PREFIX = "duckclaw:worlds:inbox:"
_INBOX_MAX = 50
_INBOX_TTL_S = 86400


def conversation_id(bot_id: str) -> str:
    """Stable playground session id for a bot. Only hex after ``admin-conv-`` (the admin console parses that shape)."""
    hexid = hashlib.sha1((bot_id or "").encode()).hexdigest()[:32]
    return f"admin-conv-{hexid}"


class SayBody(BaseModel):
    bot_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1, max_length=500)


class TranscriptItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=2000)


class TranscriptBody(BaseModel):
    bot_id: str = Field(..., min_length=1)
    items: list[TranscriptItem] = Field(..., min_length=1, max_length=20)


async def _append(request: Request, profile: dict[str, Any], bot: dict[str, Any], actor: str, items: list[dict[str, str]]) -> int:
    from core.admin_conversations import upsert_conversation_meta
    from core.chat_history import normalize_history_item, redis_load_chat_history, redis_save_chat_history

    redis_client = getattr(request.app.state, "redis", None)
    tenant, sid = profile["tenant_id"], conversation_id(bot["id"])
    # ponytail: load-append-save is not atomic; a planner turn is on another chat so only two simultaneous transcript posts could lose a line.
    saved = await redis_load_chat_history(redis_client, tenant, sid)
    saved = saved + [i for i in (normalize_history_item(x) for x in items) if i]
    await redis_save_chat_history(redis_client, tenant, sid, saved)
    await upsert_conversation_meta(redis_client, tenant_id=tenant, session_id=sid, actor=actor, section="worlds", title=f"{bot.get('name') or 'Bot'} (mundo)", message_count=len(saved), **{"user_message" if items[-1]["role"] == "user" else "assistant_message": items[-1]["content"]})
    return len(saved)


@router.post("/bots/say", dependencies=[Depends(require_admin_key)])
async def say(body: SayBody, request: Request, actor: str = Depends(actor_from_header)) -> dict:
    profile = await _profile(actor)
    bot = await _existing_bot(profile, body.bot_id)
    if bot is None:
        raise problem(404, "Bot no encontrado", body.bot_id)
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        raise problem(503, "Redis no disponible para el buzón del bot", "")
    text = " ".join(body.text.split())
    key = _INBOX_PREFIX + bot["id"]
    await redis_client.rpush(key, json.dumps({"text": text, "author": actor}, ensure_ascii=False))
    await redis_client.ltrim(key, -_INBOX_MAX, -1)
    await redis_client.expire(key, _INBOX_TTL_S)
    await _append(request, profile, bot, actor, [{"role": "user", "content": text}])
    return {"ok": True, "conversation_id": conversation_id(bot["id"])}


@router.get("/bots/inbox", dependencies=[Depends(require_admin_or_runner_key)])
async def inbox(bot_id: str, request: Request, actor: str = Depends(actor_from_header)) -> dict:
    """Drain the bot's inbox: each message is delivered once."""
    profile = await _profile(actor)
    bot = await _existing_bot(profile, bot_id)
    if bot is None:
        raise problem(404, "Bot no encontrado", bot_id)
    redis_client = getattr(request.app.state, "redis", None)
    out: list[dict] = []
    if redis_client is not None:
        key = _INBOX_PREFIX + bot["id"]
        for _ in range(_INBOX_MAX):
            raw = await redis_client.lpop(key)
            if raw is None:
                break
            try:
                out.append(json.loads(raw))
            except ValueError:
                continue
    return {"messages": out, "conversation_id": conversation_id(bot["id"])}


@router.post("/bots/transcript", dependencies=[Depends(require_admin_or_runner_key)])
async def transcript(body: TranscriptBody, request: Request, actor: str = Depends(actor_from_header)) -> dict:
    profile = await _profile(actor)
    bot = await _existing_bot(profile, body.bot_id)
    if bot is None:
        raise problem(404, "Bot no encontrado", body.bot_id)
    n = await _append(request, profile, bot, actor, [i.model_dump() for i in body.items])
    return {"ok": True, "conversation_id": conversation_id(bot["id"]), "messages": n}
