"""StateDelta helpers para assets visuales ComfyUI (producer lado workers)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from duckclaw.forge.skills.quant_state_delta import _release_ro_vault_for_remote_writer

_log = logging.getLogger(__name__)

DEFAULT_VISUAL_STATE_DELTA_QUEUE = "duckclaw:state_delta:visual"


def visual_state_delta_queue_key() -> str:
    return (os.environ.get("DUCKCLAW_VISUAL_STATE_DELTA_QUEUE") or DEFAULT_VISUAL_STATE_DELTA_QUEUE).strip()


def push_visual_state_delta_sync(payload: dict[str, Any], *, duckclaw_db: Any | None = None) -> bool:
    _release_ro_vault_for_remote_writer(payload, duckclaw_db)

    url = (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    if not url:
        _log.warning("[visual_state_delta] REDIS_URL ausente; omitiendo enqueue")
        return False
    try:
        import redis

        r = redis.from_url(url, decode_responses=True)
        r.lpush(visual_state_delta_queue_key(), json.dumps(payload, ensure_ascii=False))
        return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("[visual_state_delta] LPUSH falló: %s", exc)
        return False
