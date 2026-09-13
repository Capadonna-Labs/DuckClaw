"""Override de historial Redis tras compactar el hilo a mitad de turno.

Cuando ``summarize_chat_context`` pliega el hilo, el grafo aún tiene el
``history_for_model`` gordo en memoria. Finalize debe persistir la base
compactada (+ el turno actual), no re-inflar Redis.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_compacted_chat_history: ContextVar[list[dict[str, str]] | None] = ContextVar(
    "duckclaw_compacted_chat_history",
    default=None,
)


def set_compacted_chat_history(items: list[dict[str, Any]] | None) -> None:
    """Marca la base de historial a usar en el próximo ``persist_chat_history``."""
    if items is None:
        _compacted_chat_history.set(None)
        return
    out: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role == "human":
            role = "user"
        if role not in ("user", "assistant"):
            continue
        out.append({"role": role, "content": content})
    _compacted_chat_history.set(out)


def take_compacted_chat_history() -> list[dict[str, str]] | None:
    """Consume el override (one-shot) para no afectar turnos siguientes."""
    items = _compacted_chat_history.get()
    _compacted_chat_history.set(None)
    if items is None:
        return None
    return list(items)


def peek_compacted_chat_history() -> list[dict[str, str]] | None:
    items = _compacted_chat_history.get()
    return list(items) if items is not None else None
