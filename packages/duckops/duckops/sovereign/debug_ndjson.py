"""Instrumentación NDJSON para sesión debug (no commitear secretos)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_DEBUG_LOG = Path("/Users/workstation/Developer/duckclaw/.cursor/debug-dc7091.log")
_SESSION = "dc7091"


def agent_log(
    *,
    location: str,
    message: str,
    hypothesis_id: str,
    data: dict[str, Any] | None = None,
    run_id: str = "pre-fix",
) -> None:
    # #region agent log
    payload = {
        "sessionId": _SESSION,
        "location": location,
        "message": message,
        "hypothesisId": hypothesis_id,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
        "runId": run_id,
    }
    try:
        _DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion
