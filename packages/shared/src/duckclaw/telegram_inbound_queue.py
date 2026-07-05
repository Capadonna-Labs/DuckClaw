"""Redis queue for Telegram inbound chat invokes — consumed by DuckClaw-Gateway."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any

_log = logging.getLogger(__name__)

TELEGRAM_INBOUND_QUEUE_KEY = "duckclaw:telegram_inbound_updates"


def telegram_inbound_queue_enabled() -> bool:
    """True when ``DUCKCLAW_TELEGRAM_INBOUND_QUEUE=1`` (default off for backward compat)."""
    raw = (os.environ.get("DUCKCLAW_TELEGRAM_INBOUND_QUEUE") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _redis_client():
    import redis

    from duckclaw.runtime_env import resolve_redis_url

    return redis.from_url(resolve_redis_url(), decode_responses=True)


def _new_job_id() -> str:
    return f"tgin_{uuid.uuid4().hex[:16]}"


def enqueue_telegram_update(payload: dict[str, Any]) -> str:
    """LPUSH a normalized job dict; returns ``job_id``."""
    job_id = str(payload.get("job_id") or _new_job_id())
    body = dict(payload)
    body["job_id"] = job_id
    body.setdefault("enqueued_at", time.time())
    client = _redis_client()
    client.lpush(TELEGRAM_INBOUND_QUEUE_KEY, json.dumps(body, ensure_ascii=False))
    _log.info(
        "telegram inbound queued job_id=%s worker_id=%s tenant_id=%s chat_id=%s",
        job_id,
        body.get("worker_id"),
        body.get("tenant_id"),
        body.get("chat_id"),
    )
    return job_id


def telegram_inbound_queue_depth() -> int | None:
    try:
        client = _redis_client()
        return int(client.llen(TELEGRAM_INBOUND_QUEUE_KEY))
    except Exception:
        return None


def dequeue_telegram_update(*, block_timeout_sec: float = 2.0) -> dict[str, Any] | None:
    client = _redis_client()
    if block_timeout_sec > 0:
        item = client.brpop(TELEGRAM_INBOUND_QUEUE_KEY, timeout=max(1, int(block_timeout_sec)))
        if not item:
            return None
        _key, raw = item
    else:
        raw = client.rpop(TELEGRAM_INBOUND_QUEUE_KEY)
        if not raw:
            return None
    try:
        data = json.loads(str(raw))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError as exc:
        _log.warning("telegram inbound job parse failed: %s", exc)
        return None
