"""Contexto de sesión para tools cuant (HITL vía chat_id, StateDelta paths, evidencia OHLCV por turno)."""

from __future__ import annotations

from contextvars import ContextVar

_quant_chat_id: ContextVar[str] = ContextVar("duckclaw_quant_chat_id", default="")
_quant_db_path: ContextVar[str] = ContextVar("duckclaw_quant_db_path", default="")
_quant_tenant_id: ContextVar[str] = ContextVar("duckclaw_quant_tenant_id", default="")
_quant_user_id: ContextVar[str] = ContextVar("duckclaw_quant_user_id", default="")
_quant_evidence_tickers: ContextVar[set[str] | None] = ContextVar("duckclaw_quant_evidence_tickers", default=None)


def set_quant_tool_chat_id(chat_id: str) -> None:
    _quant_chat_id.set((chat_id or "").strip())


def get_quant_tool_chat_id() -> str:
    return (_quant_chat_id.get() or "").strip()


def set_quant_tool_db_path(path: str) -> None:
    _quant_db_path.set((path or "").strip())


def get_quant_tool_db_path() -> str:
    return (_quant_db_path.get() or "").strip()


def set_quant_tool_tenant_id(tenant_id: str) -> None:
    _quant_tenant_id.set((tenant_id or "").strip())


def get_quant_tool_tenant_id() -> str:
    return (_quant_tenant_id.get() or "").strip()


def set_quant_tool_user_id(user_id: str) -> None:
    _quant_user_id.set((user_id or "").strip())


def get_quant_tool_user_id() -> str:
    return (_quant_user_id.get() or "").strip()


def reset_quant_market_evidence() -> None:
    """Limpia tickers con ingesta OK en el turno (llamar al inicio de turno usuario → Quant Trader)."""
    _quant_evidence_tickers.set(set())


def note_quant_market_evidence_ticker(ticker: str) -> None:
    t = (ticker or "").strip().upper()
    if not t:
        return
    s = _quant_evidence_tickers.get()
    if s is None:
        s = set()
        _quant_evidence_tickers.set(s)
    s.add(t)


def has_quant_market_evidence_for_ticker(ticker: str) -> bool:
    t = (ticker or "").strip().upper()
    if not t:
        return False
    s = _quant_evidence_tickers.get()
    return bool(s and t in s)
