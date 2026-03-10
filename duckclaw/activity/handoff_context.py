"""Contexto de thread_id para HandoffTrigger (HITL)."""

from contextvars import ContextVar

_current_thread_id: ContextVar[str] = ContextVar("handoff_thread_id", default="default")


def set_handoff_thread_id(thread_id: str) -> None:
    """Establece thread_id para handoff_trigger. Llamar antes de invoke."""
    _current_thread_id.set(thread_id)


def get_handoff_thread_id() -> str:
    """Obtiene thread_id del contexto actual."""
    return _current_thread_id.get()
