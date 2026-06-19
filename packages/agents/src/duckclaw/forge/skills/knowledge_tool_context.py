"""Contexto de sesión para search_project_knowledge (tenant, proyecto, worker)."""

from __future__ import annotations

from contextvars import ContextVar

_knowledge_tenant_id: ContextVar[str] = ContextVar("duckclaw_knowledge_tenant_id", default="")
_knowledge_project_id: ContextVar[str] = ContextVar("duckclaw_knowledge_project_id", default="")
_knowledge_worker_uid: ContextVar[str] = ContextVar("duckclaw_knowledge_worker_uid", default="")


def set_knowledge_tool_tenant_id(tenant_id: str) -> None:
    _knowledge_tenant_id.set((tenant_id or "").strip() or "default")


def get_knowledge_tool_tenant_id() -> str:
    return (_knowledge_tenant_id.get() or "").strip() or "default"


def set_knowledge_tool_project_id(project_id: str) -> None:
    _knowledge_project_id.set((project_id or "").strip())


def get_knowledge_tool_project_id() -> str:
    return (_knowledge_project_id.get() or "").strip()


def set_knowledge_tool_worker_uid(worker_uid: str) -> None:
    _knowledge_worker_uid.set((worker_uid or "").strip())


def get_knowledge_tool_worker_uid() -> str:
    return (_knowledge_worker_uid.get() or "").strip()
