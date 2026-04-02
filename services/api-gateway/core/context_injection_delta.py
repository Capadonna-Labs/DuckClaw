"""StateDelta CONTEXT_INJECTION: modelos Pydantic y push a Redis."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal

from pydantic import BaseModel, Field

_log = logging.getLogger("duckclaw.gateway.context_injection_delta")

DEFAULT_CONTEXT_STATE_DELTA_QUEUE = "duckclaw:state_delta:context"


class ContextInjectionMutation(BaseModel):
    raw_text: str = Field(..., min_length=1)
    source: Literal["telegram_cmd"] = "telegram_cmd"


class ContextInjectionStateDelta(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    delta_type: Literal["CONTEXT_INJECTION"] = "CONTEXT_INJECTION"
    mutation: ContextInjectionMutation
    user_id: str = Field(..., min_length=1, description="Dueño de bóveda para validate_user_db_path")
    target_db_path: str = Field(..., min_length=1, description="DuckDB absoluta del tenant")


def context_injection_queue_key() -> str:
    return (os.environ.get("DUCKCLAW_CONTEXT_STATE_DELTA_QUEUE") or DEFAULT_CONTEXT_STATE_DELTA_QUEUE).strip()


def build_context_injection_delta(
    *,
    tenant_id: str,
    raw_text: str,
    user_id: str,
    target_db_path: str,
) -> ContextInjectionStateDelta:
    return ContextInjectionStateDelta(
        tenant_id=str(tenant_id or "").strip() or "default",
        mutation=ContextInjectionMutation(
            raw_text=str(raw_text or "").strip(),
            source="telegram_cmd",
        ),
        user_id=str(user_id or "").strip() or "default",
        target_db_path=str(target_db_path or "").strip(),
    )


async def push_context_injection_delta_redis(redis_client: Any, delta: ContextInjectionStateDelta) -> None:
    if redis_client is None:
        return
    key = context_injection_queue_key()
    payload = delta.model_dump(mode="json")
    try:
        await redis_client.lpush(key, json.dumps(payload, ensure_ascii=False))
        _log.debug("CONTEXT_INJECTION redis LPUSH ok key=%s", key)
    except Exception as exc:  # noqa: BLE001
        _log.error("CONTEXT_INJECTION redis LPUSH falló key=%s: %s", key, exc)
        raise
