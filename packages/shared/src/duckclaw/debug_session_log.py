"""Session-scoped NDJSON debug logging — disabled (no file I/O)."""

from __future__ import annotations

from typing import Any, Mapping


def agent_debug_log(
    hypothesis_id: str,
    location: str,
    message: str,
    data: Mapping[str, Any] | None = None,
    *,
    run_id: str | None = None,
) -> None:
    """No-op: reserved for optional Cursor-session NDJSON (not used in production)."""
    del hypothesis_id, location, message, data, run_id
