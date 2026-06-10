"""Enqueue meditate corrective mutations via db-writer state delta queue."""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

_log = logging.getLogger(__name__)

DEFAULT_MEDITATE_STATE_DELTA_QUEUE = "duckclaw:state_delta:meditate"
CIRCUIT_BREAKER_TTL_SECONDS = 3600


def meditate_state_delta_queue_key() -> str:
    return (
        os.environ.get("DUCKCLAW_MEDITATE_STATE_DELTA_QUEUE") or DEFAULT_MEDITATE_STATE_DELTA_QUEUE
    ).strip()


def circuit_breaker_redis_key(tenant_id: str, worker_id: str) -> str:
    t = (tenant_id or "default").strip() or "default"
    w = (worker_id or "unknown").strip() or "unknown"
    return f"duckclaw:meditate:circuit_breaker:{t}:{w}"


def push_meditate_state_delta_sync(payload: dict[str, Any]) -> bool:
    url = (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    if not url:
        _log.warning("[meditate_state_delta] REDIS_URL ausente; omitiendo enqueue")
        return False
    try:
        import redis

        r = redis.from_url(url, decode_responses=True)
        r.lpush(meditate_state_delta_queue_key(), json.dumps(payload, ensure_ascii=False))
        return True
    except Exception as exc:
        _log.warning("[meditate_state_delta] LPUSH falló: %s", exc)
        return False


def set_circuit_breaker_pause(
    tenant_id: str,
    worker_id: str,
    *,
    reason: str = "",
    ttl_seconds: int = CIRCUIT_BREAKER_TTL_SECONDS,
) -> bool:
    url = (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    if not url:
        return False
    try:
        import redis

        r = redis.from_url(url, decode_responses=True)
        key = circuit_breaker_redis_key(tenant_id, worker_id)
        body = json.dumps({"reason": reason, "tenant_id": tenant_id, "worker_id": worker_id})
        r.setex(key, max(60, int(ttl_seconds)), body)
        return True
    except Exception as exc:
        _log.warning("circuit_breaker set failed: %s", exc)
        return False


def _circuit_breaker_redis_get_sync(key: str) -> str | None:
    """Sync GET — safe from sync and async gateway contexts."""
    url = (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    if not url:
        return None
    import redis

    r = redis.from_url(url, decode_responses=True)
    try:
        val = r.get(key)
        return str(val) if val is not None else None
    finally:
        try:
            r.close()
        except Exception:
            pass


def is_circuit_breaker_active(tenant_id: str, worker_id: str, *, redis_client: Any = None) -> bool:
    del redis_client  # FastAPI pasa redis.asyncio; usar cliente sync propio
    key = circuit_breaker_redis_key(tenant_id, worker_id)
    try:
        return _circuit_breaker_redis_get_sync(key) is not None
    except Exception:
        return False


def emit_purge_stale_tasks(
    *,
    tenant_id: str,
    user_id: str,
    target_db_path: str,
    task_ids: list[str],
    source_table: str = "quant_core.trade_signals",
) -> bool:
    if not task_ids:
        return True
    return push_meditate_state_delta_sync(
        {
            "delta_type": "PURGE_STALE_TASKS",
            "tenant_id": tenant_id,
            "user_id": user_id,
            "target_db_path": target_db_path,
            "mutation": {
                "source_table": source_table,
                "task_ids": task_ids[:200],
            },
        }
    )


def emit_quarantine_memory(
    *,
    tenant_id: str,
    user_id: str,
    target_db_path: str,
    memory_ids: list[str],
) -> bool:
    if not memory_ids:
        return True
    return push_meditate_state_delta_sync(
        {
            "delta_type": "QUARANTINE_MEMORY",
            "tenant_id": tenant_id,
            "user_id": user_id,
            "target_db_path": target_db_path,
            "mutation": {"memory_ids": memory_ids[:200]},
        }
    )


def emit_meditate_audit(
    *,
    tenant_id: str,
    user_id: str,
    target_db_path: str,
    run_id: str,
    distance_vector: dict[str, float],
    actions_json: list[dict[str, Any]],
    status: str,
) -> bool:
    return push_meditate_state_delta_sync(
        {
            "delta_type": "UPSERT_MEDITATE_AUDIT",
            "tenant_id": tenant_id,
            "user_id": user_id,
            "target_db_path": target_db_path,
            "mutation": {
                "run_id": run_id or str(uuid.uuid4()),
                "distance_vector": distance_vector,
                "actions_json": actions_json,
                "status": status,
            },
        }
    )
