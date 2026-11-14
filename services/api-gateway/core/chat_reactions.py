"""Emoji reactions on chat messages: one emoji per actor (``user`` / ``agent``) per message.

Stored in a Redis hash ``duckclaw:chat_reactions:{tenant}:{session}``, field ``{msg_key}|{actor}`` -> emoji. Not DuckDB: reactions are light
metadata and the gateway already owns the chat-history Redis keys, so this does not touch the DB-Writer rule.
A message has no stable id (history is rewritten each turn), so ``msg_key`` is a hash of its role + normalized text.
ponytail: two identical messages (say two "ok") share their reactions; a stable message id would end that, and Redis durability
(same as the history) is the ceiling. Upgrade path: an ``admin_message_reactions`` table written through a typed command.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from core.chat_history import normalize_history_item

ACTORS = ("user", "agent")


def reactions_key(tenant_id: str, session_id: str) -> str:
    return f"duckclaw:chat_reactions:{(tenant_id or 'default').strip() or 'default'}:{(session_id or 'default').strip() or 'default'}"


def _ttl() -> int:
    try:
        return int(os.environ.get("DUCKCLAW_CHAT_REACTIONS_TTL_SEC", str(90 * 86400)))
    except ValueError:
        return 90 * 86400


def msg_key(role: str, text: str) -> str | None:
    """Stable fingerprint of a message as the history stores it; None for an empty or non user/assistant message."""
    item = normalize_history_item({"role": role, "content": text})
    if not item:
        return None
    return hashlib.sha1(f"{item['role']}\n{item['content']}".encode("utf-8")).hexdigest()[:12]


def valid_emoji(emoji: Any) -> str | None:
    """The emoji trimmed, or None when it is empty, long, or plain ASCII text (a reaction is a pictograph, not a word)."""
    e = str(emoji or "").strip()
    return e if 0 < len(e) <= 16 and not e.isascii() else None


async def set_reaction(redis: Any, tenant_id: str, session_id: str, role: str, text: str, actor: str, emoji: str | None) -> bool:
    """Set (or, with ``emoji`` None, remove) one actor's reaction on a message. False when it could not be applied."""
    k = msg_key(role, text)
    if redis is None or k is None or actor not in ACTORS:
        return False
    key, field = reactions_key(tenant_id, session_id), f"{k}|{actor}"
    try:
        if emoji is None:
            await redis.hdel(key, field)
        else:
            await redis.hset(key, field, emoji)
            await redis.expire(key, _ttl())
        return True
    except Exception:
        return False


async def load_reactions(redis: Any, tenant_id: str, session_id: str) -> dict[str, list[dict[str, str]]]:
    """``{msg_key: [{"emoji", "by"}]}`` for a conversation; empty on any Redis problem (reactions never block a chat)."""
    if redis is None:
        return {}
    try:
        raw = await redis.hgetall(reactions_key(tenant_id, session_id))
    except Exception:
        return {}
    out: dict[str, list[dict[str, str]]] = {}
    for f, e in (raw or {}).items():
        f = f.decode() if isinstance(f, bytes) else str(f)
        e = e.decode() if isinstance(e, bytes) else str(e)
        k, _, actor = f.partition("|")
        if k and actor in ACTORS and e:
            out.setdefault(k, []).append({"emoji": e, "by": actor})
    return out


def attach_reactions(messages: list[dict[str, Any]], reactions: dict[str, list[dict[str, str]]]) -> list[dict[str, Any]]:
    """Adds ``reactions`` to each message that has some (in place; returns the list)."""
    if not reactions:
        return messages
    for m in messages:
        k = msg_key(str(m.get("role") or ""), str(m.get("content") if m.get("content") is not None else m.get("text") or ""))
        if k in reactions:
            m["reactions"] = reactions[k]
    return messages


def annotate_history_for_model(history: list[dict[str, Any]], reactions: dict[str, list[dict[str, str]]]) -> list[dict[str, Any]]:
    """Copy of ``history`` where an assistant message the user reacted to ends with a note saying so, so the agent can read it.
    Only for this turn's graph input: the stored history is never annotated."""
    if not reactions or not history:
        return history
    out = []
    for h in history:
        k = msg_key(str(h.get("role") or ""), str(h.get("content") or "")) if h.get("role") == "assistant" else None
        mine = [r["emoji"] for r in reactions.get(k, []) if r["by"] == "user"] if k else []
        out.append({**h, "content": f"{h.get('content', '')}\n[El usuario reaccionó a este mensaje con {' '.join(mine)}]"} if mine else h)
    return out


async def pop_pending_interim_messages(redis: Any, tenant_id: str, session_id: str) -> list[dict[str, Any]]:
    """History items for the interim messages the agent sent this turn (``send_interim_message``), oldest first; clears the queue.
    ponytail: if a turn ends without persisting (empty reply) they wait in Redis until their 10 min TTL; a stable turn id would end that."""
    if redis is None:
        return []
    try:
        from duckclaw.forge.skills.react_to_message_bridge import pending_interim_key

        key = pending_interim_key(tenant_id, session_id)
        raw = await redis.lrange(key, 0, -1)
        if not raw:
            return []
        await redis.delete(key)
    except Exception:
        return []
    items = (normalize_history_item({"role": "assistant", "content": r.decode() if isinstance(r, bytes) else r}) for r in raw)
    return [i for i in items if i]


async def apply_pending_agent_reaction(redis: Any, tenant_id: str, session_id: str, user_text: str) -> None:
    """Applies the emoji the agent queued with ``react_to_message`` this turn to the user's message, then clears it. Never raises."""
    if redis is None:
        return
    try:
        from duckclaw.forge.skills.react_to_message_bridge import pending_reaction_key

        key = pending_reaction_key(tenant_id, session_id)
        raw = await redis.get(key)
        if not raw:
            return
        await redis.delete(key)
        emoji = valid_emoji(raw.decode() if isinstance(raw, bytes) else raw)
        if emoji:
            await set_reaction(redis, tenant_id, session_id, "user", user_text, "agent", emoji)
    except Exception:
        return
