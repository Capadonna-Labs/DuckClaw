"""Worlds: a bot's slow, deliberate thinking runs on a DuckClaw worker.

A runner keeps its fast reflexes local and sends here the turns that are worth a worker's skills, knowledge and memory (planning what to do next). The gateway runs
the turn on the worker named in the bot's own settings (``planner_worker``, ``research_worker`` when the call's purpose is ``research``: web search and sandbox for a
question the runner cannot answer alone, or ``journal_worker`` for ``journal``: writing the bot's logbook; never a worker the caller names) through the same chat path as the admin playground, as the bot's owner, and returns the reply. The runner key opens this call like the other two runner calls; because a turn spends model tokens, each bot is capped per minute
(``DUCKCLAW_WORLD_THINK_PER_MIN``, default 20; research turns ``DUCKCLAW_WORLD_RESEARCH_PER_MIN``, default 4, they search the web) and the worker's own per-turn spend
cap still applies.
"""

from __future__ import annotations

import os
import re
import time
from collections import defaultdict, deque
from typing import Literal

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
    purpose: Literal["plan", "research", "journal"] = "plan"     # picks WHICH of the bot's own settings names the worker; the worker id is never sent by the caller


_SETTING = {"plan": "planner_worker", "research": "research_worker", "journal": "journal_worker"}


def _per_minute(purpose: str = "plan") -> int:
    env, default = {"research": ("DUCKCLAW_WORLD_RESEARCH_PER_MIN", 4), "journal": ("DUCKCLAW_WORLD_JOURNAL_PER_MIN", 4)}.get(purpose, ("DUCKCLAW_WORLD_THINK_PER_MIN", 20))
    try:
        return max(1, int(os.environ.get(env) or default))
    except ValueError:
        return default


def _allow(bot_id: str, purpose: str = "plan") -> bool:
    """Sliding one-minute window per bot, in process: the gateway is a single process and a restart only resets the counter."""
    now = time.monotonic()
    calls = _CALLS[bot_id if purpose == "plan" else f"{bot_id}:{purpose}"]
    while calls and now - calls[0] > 60:
        calls.popleft()
    if len(calls) >= _per_minute(purpose):
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
    setting = _SETTING[body.purpose]
    worker = str(bot["settings"].get(setting) or "").strip()
    if not _WORKER_ID.match(worker):
        raise problem(409, f"{setting} no configurado en los ajustes del bot", "")
    if not _allow(body.bot_id, body.purpose):
        raise problem(429, "Demasiados turnos por minuto para este bot", str(_per_minute(body.purpose)))

    chat = PlaygroundChatBody(worker_id=worker, message=body.message, chat_id=(body.chat_id or f"world-{body.bot_id}")[:128], tenant_id=profile["tenant_id"])
    started = time.monotonic()
    prepared = await chat_turn.prepare_playground_chat_turn(chat, actor=actor, request=request)
    result = await chat_turn.invoke_playground_chat_sync(prepared, request=request, notify=False)
    payload = chat_turn.format_playground_chat_payload(prepared, result)
    return {"ok": True, "worker_id": worker, "response": payload.get("response", ""), "usage_tokens": payload.get("usage_tokens"),
            "ms": int((time.monotonic() - started) * 1000)}
