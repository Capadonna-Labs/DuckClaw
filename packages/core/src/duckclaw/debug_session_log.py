"""Session-scoped NDJSON debug logging (write-only, no secrets)."""
from __future__ import annotations

import json
import time
from typing import Any, Mapping

_DEBUG_LOG_PATH = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log"
_DEBUG_SESSION = "c964f7"


def agent_debug_log(
    location: str,
    message: str,
    data: Mapping[str, Any] | None = None,
    *,
    hypothesis_id: str = "H0",
    run_id: str = "pre",
) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": _DEBUG_SESSION,
            "id": f"log_{int(time.time() * 1000)}",
            "timestamp": int(time.time() * 1000),
            "location": location,
            "message": message,
            "data": dict(data) if data else {},
            "runId": run_id,
            "hypothesisId": hypothesis_id,
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion
