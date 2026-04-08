"""StateDelta helpers para Quant Trader (producer lado workers)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

_log = logging.getLogger(__name__)

DEFAULT_QUANT_STATE_DELTA_QUEUE = "duckclaw:state_delta:quant"


def quant_state_delta_queue_key() -> str:
    return (os.environ.get("DUCKCLAW_QUANT_STATE_DELTA_QUEUE") or DEFAULT_QUANT_STATE_DELTA_QUEUE).strip()


def push_quant_state_delta_sync(payload: dict[str, Any]) -> bool:
    url = (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    if not url:
        _log.warning("[quant_state_delta] REDIS_URL ausente; omitiendo enqueue")
        return False
    try:
        import redis

        r = redis.from_url(url, decode_responses=True)
        r.lpush(quant_state_delta_queue_key(), json.dumps(payload, ensure_ascii=False))
        return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("[quant_state_delta] LPUSH falló: %s", exc)
        return False
