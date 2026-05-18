"""Heartbeats de chat admin → SSE (Redis pub/sub), sin egress Telegram."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

_log = logging.getLogger(__name__)

ADMIN_HEARTBEAT_CHANNEL_PREFIX = "duckclaw:admin-heartbeat:"


def admin_heartbeat_channel(chat_id: str) -> str:
    cid = str(chat_id or "").strip() or "unknown"
    return f"{ADMIN_HEARTBEAT_CHANNEL_PREFIX}{cid}"


def parse_admin_heartbeat_payload(raw: str) -> dict[str, Any] | None:
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    text = str(data.get("text") or "").strip()
    if not text:
        return None
    kind = str(data.get("kind") or "status").strip() or "status"
    out: dict[str, Any] = {"text": text, "kind": kind}
    wid = str(data.get("worker_id") or "").strip()
    if wid:
        out["worker_id"] = wid
    raw_slot = data.get("swarm_slot")
    if raw_slot is not None:
        try:
            out["swarm_slot"] = max(1, int(raw_slot))
        except (TypeError, ValueError):
            out["swarm_slot"] = 1
    return out


async def iter_admin_heartbeats(
    redis_client: Any,
    chat_id: str,
    *,
    stop: asyncio.Event | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Escucha pub/sub hasta que ``stop`` se active o se cancele la tarea."""
    if redis_client is None:
        return
    channel = admin_heartbeat_channel(chat_id)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    try:
        while stop is None or not stop.is_set():
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.25)
            if not msg:
                await asyncio.sleep(0.05)
                continue
            if msg.get("type") != "message":
                continue
            data = msg.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")
            parsed = parse_admin_heartbeat_payload(str(data or ""))
            if parsed:
                yield parsed
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _log.debug("admin heartbeat listener stopped chat_id=%r: %s", chat_id, exc)
    finally:
        try:
            await pubsub.unsubscribe(channel)
        except Exception:
            pass
        try:
            await pubsub.aclose()
        except Exception:
            pass
