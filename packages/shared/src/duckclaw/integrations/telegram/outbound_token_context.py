# packages/shared/src/duckclaw/integrations/telegram/outbound_token_context.py
"""ContextVar del token Bot API para esta tarea async (multiplex webhook sin pisar os.environ)."""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

_var: ContextVar[str | None] = ContextVar("duckclaw_telegram_bot_token_override", default=None)


def effective_telegram_bot_token_outbound() -> str:
    """Token para envíos salientes: override por request si existe, si no ``TELEGRAM_BOT_TOKEN``."""
    o = _var.get()
    if o and o.strip():
        return o.strip()
    return (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()


@contextmanager
def telegram_bot_token_override(token: str) -> Iterator[None]:
    """Fija el token solo para el hilo/contexto actual (compatible con ``asyncio.create_task``)."""
    t = (token or "").strip()
    if not t:
        yield
        return
    reset: Token[str | None] = _var.set(t)
    try:
        yield
    finally:
        _var.reset(reset)
