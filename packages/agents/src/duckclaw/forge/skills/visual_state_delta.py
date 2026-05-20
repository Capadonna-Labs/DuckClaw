"""StateDelta helpers para assets visuales ComfyUI (producer lado workers)."""

from __future__ import annotations

import json
import logging
import os
from contextvars import ContextVar
from typing import Any

from duckclaw.forge.skills.quant_state_delta import _release_ro_vault_for_remote_writer

_log = logging.getLogger(__name__)

# Hub RO del manager (finanzdb1, etc.) durante delegación visual: libera lock para db-writer.
_visual_hub_db_for_writer: ContextVar[Any] = ContextVar("duckclaw_visual_hub_db_for_writer", default=None)


def set_visual_state_delta_hub_db(db: Any | None) -> None:
    _visual_hub_db_for_writer.set(db)


def get_visual_state_delta_hub_db() -> Any | None:
    return _visual_hub_db_for_writer.get()


def clear_visual_state_delta_hub_db() -> None:
    _visual_hub_db_for_writer.set(None)

DEFAULT_VISUAL_STATE_DELTA_QUEUE = "duckclaw:state_delta:visual"


def visual_state_delta_queue_key() -> str:
    return (os.environ.get("DUCKCLAW_VISUAL_STATE_DELTA_QUEUE") or DEFAULT_VISUAL_STATE_DELTA_QUEUE).strip()


def push_visual_state_delta_sync(payload: dict[str, Any], *, duckclaw_db: Any | None = None) -> bool:
    hub_db = get_visual_state_delta_hub_db()
    if hub_db is not None:
        _release_ro_vault_for_remote_writer(payload, hub_db)
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
