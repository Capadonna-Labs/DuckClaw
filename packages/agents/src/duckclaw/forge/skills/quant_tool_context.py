"""Contexto de sesión para tools cuant (HITL vía chat_id, StateDelta paths, evidencia OHLCV por turno)."""

from __future__ import annotations

import json
import threading
import time
from contextvars import ContextVar

_quant_chat_id: ContextVar[str] = ContextVar("duckclaw_quant_chat_id", default="")
_quant_db_path: ContextVar[str] = ContextVar("duckclaw_quant_db_path", default="")
_quant_tenant_id: ContextVar[str] = ContextVar("duckclaw_quant_tenant_id", default="")
_quant_user_id: ContextVar[str] = ContextVar("duckclaw_quant_user_id", default="")

# Evidencia OHLCV por turno: proceso global (no ContextVar) porque LangGraph/async puede
# ejecutar nodos/herramientas en hilos distintos y el set en ContextVar no se comparte.
_evidence_lock = threading.Lock()
_evidence_by_chat: dict[str, set[str]] = {}
_tls_evidence_chat: threading.local = threading.local()

_DEBUG_LOG_PATH = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log"


def _agent_debug_log(hypothesis_id: str, location: str, message: str, data: dict[str, object]) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": "c964f7",
            "timestamp": int(time.time() * 1000),
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": {**data, "thread": threading.get_ident()},
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as _f:
            _f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion


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


def bind_quant_market_evidence_chat(chat_id: str) -> None:
    """Fija el chat_id usado para evidencia OHLCV en este hilo (llamar al inicio de agent/tools)."""
    cid = (chat_id or "").strip()
    _tls_evidence_chat.chat_id = cid if cid else None


def _evidence_bucket_key() -> str:
    tls = getattr(_tls_evidence_chat, "chat_id", None)
    if isinstance(tls, str) and tls.strip():
        return tls.strip()
    return (get_quant_tool_chat_id() or "").strip() or "__default__"


def reset_quant_market_evidence() -> None:
    """Limpia tickers con ingesta OK en el turno (tras bind_quant_market_evidence_chat + turno Human)."""
    k = _evidence_bucket_key()
    with _evidence_lock:
        _evidence_by_chat[k] = set()
    # #region agent log
    _agent_debug_log(
        "H2",
        "quant_tool_context.reset_quant_market_evidence",
        "cleared bucket",
        {"key": k},
    )
    # #endregion


def note_quant_market_evidence_ticker(ticker: str) -> None:
    t = (ticker or "").strip().upper()
    if not t:
        return
    k = _evidence_bucket_key()
    with _evidence_lock:
        if k not in _evidence_by_chat:
            _evidence_by_chat[k] = set()
        _evidence_by_chat[k].add(t)
        _sz = len(_evidence_by_chat[k])
    # #region agent log
    _agent_debug_log(
        "H1",
        "quant_tool_context.note_quant_market_evidence_ticker",
        "noted ticker",
        {"key": k, "ticker": t, "size": _sz},
    )
    # #endregion


def has_quant_market_evidence_for_ticker(ticker: str) -> bool:
    t = (ticker or "").strip().upper()
    if not t:
        return False
    k = _evidence_bucket_key()
    with _evidence_lock:
        s = _evidence_by_chat.get(k)
        ok = bool(s and t in s)
    # #region agent log
    _agent_debug_log(
        "H1",
        "quant_tool_context.has_quant_market_evidence_for_ticker",
        "check",
        {"key": k, "ticker": t, "has": ok},
    )
    # #endregion
    return ok
