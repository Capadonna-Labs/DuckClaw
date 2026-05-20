"""Reservado para instrumentación opcional en desarrollo (no-op en producción)."""

from __future__ import annotations

from typing import Any


def agent_log(
    *,
    location: str,
    message: str,
    hypothesis_id: str,
    data: dict[str, Any] | None = None,
    run_id: str = "pre-fix",
) -> None:
    """No-op."""
