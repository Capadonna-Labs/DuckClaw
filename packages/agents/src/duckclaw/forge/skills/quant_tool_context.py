"""Contexto de sesión para tools cuant (execute_order necesita chat_id)."""

from __future__ import annotations

from contextvars import ContextVar

_quant_chat_id: ContextVar[str] = ContextVar("duckclaw_quant_chat_id", default="")


def set_quant_tool_chat_id(chat_id: str) -> None:
    _quant_chat_id.set((chat_id or "").strip())


def get_quant_tool_chat_id() -> str:
    return (_quant_chat_id.get() or "").strip()
