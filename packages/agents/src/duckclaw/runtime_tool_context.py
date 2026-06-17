"""Thread-local runtime context for tool invocations (framework-native)."""

from __future__ import annotations

from typing import Any

_CONTEXT: dict[str, str] = {
    "tenant_id": "",
    "user_id": "",
    "chat_id": "",
    "worker_id": "",
    "db_path": "",
}


def tool_tenant_id() -> str:
    return (_CONTEXT.get("tenant_id") or "").strip()


def tool_user_id() -> str:
    return (_CONTEXT.get("user_id") or "").strip()


def tool_chat_id() -> str:
    return (_CONTEXT.get("chat_id") or "").strip()


def tool_worker_id() -> str:
    return (_CONTEXT.get("worker_id") or "").strip()


def tool_db_path() -> str:
    return (_CONTEXT.get("db_path") or "").strip()


def set_tool_context(
    *,
    tenant_id: str = "",
    user_id: str = "",
    chat_id: str = "",
    worker_id: str = "",
    db_path: str = "",
) -> None:
    if tenant_id:
        _CONTEXT["tenant_id"] = (tenant_id or "default").strip() or "default"
    if user_id:
        _CONTEXT["user_id"] = (user_id or "default").strip() or "default"
    if chat_id:
        _CONTEXT["chat_id"] = str(chat_id).strip()
    if worker_id:
        _CONTEXT["worker_id"] = str(worker_id).strip()
    if db_path:
        _CONTEXT["db_path"] = str(db_path).strip()


def merge_tool_context(**kwargs: Any) -> dict[str, str]:
    tenant_id = str(kwargs.get("tenant_id") or tool_tenant_id() or "default").strip() or "default"
    user_id = str(kwargs.get("user_id") or tool_user_id() or tenant_id).strip() or tenant_id
    chat_id = str(kwargs.get("chat_id") or tool_chat_id() or "").strip()
    worker_id = str(kwargs.get("worker_id") or tool_worker_id() or "").strip()
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "chat_id": chat_id,
        "worker_id": worker_id,
    }
