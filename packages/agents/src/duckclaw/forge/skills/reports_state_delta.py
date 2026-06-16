"""StateDelta helpers para custom reports (producer lado workers)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from duckclaw.state_delta_vault import release_ro_vault_for_remote_writer

_log = logging.getLogger(__name__)

DEFAULT_REPORTS_STATE_DELTA_QUEUE = "duckclaw:state_delta:reports"


def reports_state_delta_queue_key() -> str:
    return (os.environ.get("DUCKCLAW_REPORTS_STATE_DELTA_QUEUE") or DEFAULT_REPORTS_STATE_DELTA_QUEUE).strip()


def push_reports_state_delta_sync(payload: dict[str, Any], *, duckclaw_db: Any | None = None) -> bool:
    from duckclaw.spawn_inline_delta import apply_reports_state_delta_message_sync
    from duckclaw.spawn_profile import spawn_inline_writes_enabled

    release_ro_vault_for_remote_writer(payload, duckclaw_db)

    if spawn_inline_writes_enabled():
        try:
            msg = json.dumps(payload, ensure_ascii=False)
            if apply_reports_state_delta_message_sync(msg):
                return True
            _log.warning("[reports_state_delta] inline apply falló (spawn profile)")
            return False
        except Exception as exc:  # noqa: BLE001
            _log.warning("[reports_state_delta] inline apply error: %s", exc)
            return False

    url = (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    if not url:
        _log.warning("[reports_state_delta] REDIS_URL ausente; omitiendo enqueue")
        return False
    try:
        import redis

        r = redis.from_url(url, decode_responses=True)
        r.lpush(reports_state_delta_queue_key(), json.dumps(payload, ensure_ascii=False))
        return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("[reports_state_delta] LPUSH falló: %s", exc)
        return False
