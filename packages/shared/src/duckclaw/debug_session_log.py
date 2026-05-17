"""NDJSON de depuración (sesión Cursor); no usar en producción."""

from __future__ import annotations

import json
import time
from typing import Any

_DEBUG_LOG_PATH = "/Users/workstation/Developer/duckclaw/.cursor/debug-dc7091.log"


def agent_debug_log(
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, Any] | None = None,
    *,
    run_id: str | None = None,
) -> None:
    # #region agent log
    try:
        payload: dict[str, Any] = {
            "sessionId": "dc7091",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        if run_id:
            payload["runId"] = run_id
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion
