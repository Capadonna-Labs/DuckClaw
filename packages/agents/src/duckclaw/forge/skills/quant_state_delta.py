"""StateDelta helpers para Quant Trader (producer lado workers)."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

_log = logging.getLogger(__name__)

DEFAULT_QUANT_STATE_DELTA_QUEUE = "duckclaw:state_delta:quant"

_DEBUG_AGENT_LOG_PATH = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-489624.log"


def quant_state_delta_queue_key() -> str:
    return (os.environ.get("DUCKCLAW_QUANT_STATE_DELTA_QUEUE") or DEFAULT_QUANT_STATE_DELTA_QUEUE).strip()


def _same_vault_db_path(lhs: str, rhs: str) -> bool:
    a, b = (lhs or "").strip(), (rhs or "").strip()
    if not a or not b:
        return False
    if a == b:
        return True
    try:
        return os.path.realpath(a) == os.path.realpath(b)
    except OSError:
        return False


def _release_ro_vault_for_remote_writer(payload: dict[str, Any], duckclaw_db: Any | None) -> bool:
    """
    Cierra el handle RO del gateway/worker sobre el mismo .duckdb que recibirá el db-writer,
    para que DuckDB permita abrir RW en el proceso writer (encolado vía Redis).
    """
    if duckclaw_db is None:
        return False
    tgt = str(payload.get("target_db_path") or "").strip()
    db_path = str(getattr(duckclaw_db, "_path", "") or "").strip()
    if not _same_vault_db_path(tgt, db_path):
        return False
    if not bool(getattr(duckclaw_db, "_read_only", False)):
        return False
    susp = getattr(duckclaw_db, "suspend_readonly_file_handle", None)
    if not callable(susp):
        return False
    try:
        susp()
        return True
    except Exception:
        return False


def push_quant_state_delta_sync(payload: dict[str, Any], *, duckclaw_db: Any | None = None) -> bool:
    suspended = _release_ro_vault_for_remote_writer(payload, duckclaw_db)

    # region agent log
    try:
        _line = json.dumps(
            {
                "sessionId": "489624",
                "hypothesisId": "A_B",
                "location": "quant_state_delta.py:push_quant_state_delta_sync",
                "message": "pre_lpush_quant_delta",
                "data": {
                    "delta_type": payload.get("delta_type"),
                    "suspend_for_writer": suspended,
                    "has_duckclaw_db": duckclaw_db is not None,
                },
                "timestamp": int(time.time() * 1000),
            },
            ensure_ascii=False,
        )
        with open(_DEBUG_AGENT_LOG_PATH, "a", encoding="utf-8") as _df:
            _df.write(_line + "\n")
    except Exception:
        pass
    # endregion

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
