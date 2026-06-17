"""StateDelta helpers for CONTEXT_INJECTION (producer side)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from duckclaw.state_delta_vault import release_ro_vault_for_remote_writer

_log = logging.getLogger(__name__)

DEFAULT_CONTEXT_STATE_DELTA_QUEUE = "duckclaw:state_delta:context"


def context_state_delta_queue_key() -> str:
    return (
        os.environ.get("DUCKCLAW_CONTEXT_STATE_DELTA_QUEUE") or DEFAULT_CONTEXT_STATE_DELTA_QUEUE
    ).strip()


def push_context_injection_sync(payload: dict[str, Any], *, duckclaw_db: Any | None = None) -> bool:
    from duckclaw.spawn_inline_delta import apply_context_injection_message_sync
    from duckclaw.spawn_profile import spawn_inline_writes_enabled

    release_ro_vault_for_remote_writer(payload, duckclaw_db)

    if spawn_inline_writes_enabled():
        try:
            msg = json.dumps(payload, ensure_ascii=False)
            if apply_context_injection_message_sync(msg):
                return True
            _log.warning("[context_injection_delta] inline apply falló (spawn profile)")
            return False
        except Exception as exc:  # noqa: BLE001
            _log.warning("[context_injection_delta] inline apply error: %s", exc)
            return False

    url = (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    if not url:
        _log.warning("[context_injection_delta] REDIS_URL ausente; omitiendo enqueue")
        return False
    try:
        import redis

        r = redis.from_url(url, decode_responses=True)
        r.lpush(context_state_delta_queue_key(), json.dumps(payload, ensure_ascii=False))
        return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("[context_injection_delta] LPUSH falló: %s", exc)
        return False
