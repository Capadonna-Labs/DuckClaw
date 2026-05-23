"""Session-scoped NDJSON debug logging for Cursor debug mode."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Mapping

_DEFAULT_LOG_PATH = (
    "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-fd1dbb.log"
)


def agent_debug_log(
    hypothesis_id: str,
    location: str,
    message: str,
    data: Mapping[str, Any] | None = None,
    *,
    run_id: str | None = None,
) -> None:
    """Append one NDJSON line when DUCKCLAW_CURSOR_DEBUG_LOG is set (or default path exists)."""
    log_path = (os.environ.get("DUCKCLAW_CURSOR_DEBUG_LOG") or "").strip() or _DEFAULT_LOG_PATH
    if not log_path:
        return
    session_id = (os.environ.get("DUCKCLAW_CURSOR_DEBUG_SESSION") or "fd1dbb").strip()
    payload: dict[str, Any] = {
        "sessionId": session_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": dict(data or {}),
        "timestamp": int(time.time() * 1000),
    }
    if run_id:
        payload["runId"] = run_id
    try:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass
