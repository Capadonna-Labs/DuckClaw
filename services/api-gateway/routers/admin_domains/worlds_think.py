"""Worlds: a bot's slow, deliberate thinking runs on a DuckClaw worker.

A runner keeps its fast reflexes local and sends here the turns that are worth a worker's skills, knowledge and memory (planning what to do next). The gateway runs
the turn on the worker named in the bot's own settings (``planner_worker``, never one the caller picks) through the same chat path as the admin playground, as the
bot's owner, and returns the reply. The runner key opens this call like the other two runner calls; because a turn spends model tokens, each bot is capped per minute
(``DUCKCLAW_WORLD_THINK_PER_MIN``, default 20) and the worker's own per-turn spend cap still applies.
"""

from __future__ import annotations

import os
import re
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import actor_from_header, problem
from routers.admin_domains.worlds import _existing_bot, _profile, require_admin_or_runner_key

router = APIRouter(prefix="/worlds", tags=["admin-worlds"])

_WORKER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CALLS: dict[str, deque[float]] = defaultdict(deque)


class ThinkBody(BaseModel):
    bot_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, max_length=16000)
    chat_id: str | None = Field(default=None, max_length=128)


def _per_minute() -> int:
    try:
        return max(1, int(os.environ.get("DUCKCLAW_WORLD_THINK_PER_MIN") or "20"))
    except ValueError:
        return 20


def _allow(bot_id: str) -> bool:
    """Sliding one-minute window per bot, in process: the gateway is a single process and a restart only resets the counter."""
    now = time.monotonic()
    calls = _CALLS[bot_id]
    while calls and now - calls[0] > 60:
        calls.popleft()
    if len(calls) >= _per_minute():
        return False
    calls.append(now)
    return True


@router.post("/think", dependencies=[Depends(require_admin_or_runner_key)])
async def think(body: ThinkBody, request: Request, actor: str = Depends(actor_from_header)) -> dict:
    from routers.admin_domains.playground import chat_turn
    from routers.admin_domains.playground.schemas import PlaygroundChatBody

    profile = await _profile(actor)
    bot = await _existing_bot(profile, body.bot_id)
    if bot is None:
        raise problem(404, "Bot no encontrado", body.bot_id)
    if not bot["enabled"]:
        raise problem(409, "Bot deshabilitado", body.bot_id)
    worker = str(bot["settings"].get("planner_worker") or "").strip()
    if not _WORKER_ID.match(worker):
        raise problem(409, "planner_worker no configurado en los ajustes del bot", "")
    if not _allow(body.bot_id):
        raise problem(429, "Demasiados turnos por minuto para este bot", str(_per_minute()))

    chat = PlaygroundChatBody(worker_id=worker, message=body.message, chat_id=(body.chat_id or f"world-{body.bot_id}")[:128], tenant_id=profile["tenant_id"])
    started = time.monotonic()
    prepared = await chat_turn.prepare_playground_chat_turn(chat, actor=actor, request=request)
    result = await chat_turn.invoke_playground_chat_sync(prepared, request=request)
    payload = chat_turn.format_playground_chat_payload(prepared, result)
    return {"ok": True, "worker_id": worker, "response": payload.get("response", ""), "usage_tokens": payload.get("usage_tokens"),
            "ms": int((time.monotonic() - started) * 1000)}
