"""Contexto de sesión para tools de /crons (chat_id, bóveda, worker)."""

from __future__ import annotations

from contextvars import ContextVar

_goals_chat_id: ContextVar[str] = ContextVar("duckclaw_goals_chat_id", default="")
_goals_db_path: ContextVar[str] = ContextVar("duckclaw_goals_db_path", default="")
_goals_worker_id: ContextVar[str] = ContextVar("duckclaw_goals_worker_id", default="")


def set_goals_tool_chat_id(chat_id: str) -> None:
    _goals_chat_id.set((chat_id or "").strip())


def get_goals_tool_chat_id() -> str:
    return (_goals_chat_id.get() or "").strip()


def set_goals_tool_db_path(path: str) -> None:
    _goals_db_path.set((path or "").strip())


def get_goals_tool_db_path() -> str:
    return (_goals_db_path.get() or "").strip()


def set_goals_tool_worker_id(worker_id: str) -> None:
    _goals_worker_id.set((worker_id or "").strip())


def get_goals_tool_worker_id() -> str:
    return (_goals_worker_id.get() or "").strip()
