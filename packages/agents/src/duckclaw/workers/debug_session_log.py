"""Optional NDJSON debug sink for active agent debug sessions (env-driven, domain-agnostic)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def append_debug_session_log(payload: dict[str, Any]) -> None:
    """
    Append one NDJSON line when ``DUCKCLAW_DEBUG_LOG`` points to a writable file.

    Host/runtime sets the path; framework code never hardcodes extension checkout locations.
    """
    log_path_raw = str(os.environ.get("DUCKCLAW_DEBUG_LOG") or "").strip()
    if not log_path_raw:
        session_id = str(payload.get("sessionId") or "").strip()
        if session_id:
            log_path_raw = str(Path.cwd() / f"debug-{session_id}.log")
        else:
            return
    try:
        with Path(log_path_raw).open("a", encoding="utf-8") as log_handle:
            log_handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        return


__all__ = ["append_debug_session_log"]
