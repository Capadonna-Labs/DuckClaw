"""NDJSON debug logs for Cursor debug mode (session 77cb49). Remove after verification."""

from __future__ import annotations

import json
import time
from typing import Any

_DEBUG_LOG_PATH = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-fd1dbb.log"
_SESSION_ID = "fd1dbb"


def agent_debug_log(
    *,
    location: str,
    message: str,
    data: dict[str, Any] | None = None,
    hypothesis_id: str = "",
    run_id: str = "pre-fix",
) -> None:
    # #region agent log
    try:
        payload: dict[str, Any] = {
            "sessionId": _SESSION_ID,
            "timestamp": int(time.time() * 1000),
            "location": location,
            "message": message,
            "data": data or {},
            "hypothesisId": hypothesis_id,
            "runId": run_id,
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion
