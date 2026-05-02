"""Session-scoped NDJSON debug logging — disabled (no file I/O)."""
from __future__ import annotations

from typing import Any, Mapping


def agent_debug_log(
    location: str,
    message: str,
    data: Mapping[str, Any] | None = None,
    *,
    hypothesis_id: str = "H0",
    run_id: str = "pre",
) -> None:
    """No-op: reserved for optional Cursor-session NDJSON (not used in production)."""
    del location, message, data, hypothesis_id, run_id
