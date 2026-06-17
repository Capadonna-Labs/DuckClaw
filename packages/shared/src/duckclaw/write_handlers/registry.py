"""Registry for typed DuckDB write command handlers.

Vertical packages register handlers at import time via :func:`register_handler`
without editing the central dispatcher module.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

Handler = Callable[[Any, dict], None]

_HANDLERS: dict[str, Handler] = {}


def register_handler(command_type: str, handler: Handler) -> None:
    """Register a handler for ``command_type`` (overwrites on duplicate)."""
    key = str(command_type).strip()
    if not key:
        raise ValueError("command_type required")
    _HANDLERS[key] = handler


def registered_handlers() -> dict[str, Handler]:
    """Return the live handler map (for dispatch and introspection)."""
    return _HANDLERS
