"""Contexto de sesión para tools cuant (execute_order necesita chat_id)."""

from __future__ import annotations

from contextvars import ContextVar

_quant_chat_id: ContextVar[str] = ContextVar("duckclaw_quant_chat_id", default="")
_quant_tenant_id: ContextVar[str] = ContextVar("duckclaw_quant_tenant_id", default="")
_quant_user_id: ContextVar[str] = ContextVar("duckclaw_quant_user_id", default="")
_quant_db_path: ContextVar[str] = ContextVar("duckclaw_quant_db_path", default="")
_quant_market_evidence_ticker: ContextVar[str] = ContextVar("duckclaw_quant_market_evidence_ticker", default="")


def set_quant_tool_chat_id(chat_id: str) -> None:
    _quant_chat_id.set((chat_id or "").strip())


def get_quant_tool_chat_id() -> str:
    return (_quant_chat_id.get() or "").strip()


def set_quant_tool_tenant_id(tenant_id: str) -> None:
    _quant_tenant_id.set((tenant_id or "").strip())


def get_quant_tool_tenant_id() -> str:
    return (_quant_tenant_id.get() or "").strip()


def set_quant_tool_user_id(user_id: str) -> None:
    _quant_user_id.set((user_id or "").strip())


def get_quant_tool_user_id() -> str:
    return (_quant_user_id.get() or "").strip()


def set_quant_tool_db_path(db_path: str) -> None:
    _quant_db_path.set((db_path or "").strip())


def get_quant_tool_db_path() -> str:
    return (_quant_db_path.get() or "").strip()


def note_quant_market_evidence_ticker(ticker: str) -> None:
    _quant_market_evidence_ticker.set((ticker or "").strip().upper())


def has_quant_market_evidence_for_ticker(ticker: str) -> bool:
    got = (_quant_market_evidence_ticker.get() or "").strip().upper()
    want = (ticker or "").strip().upper()
    return bool(got and want and got == want)
