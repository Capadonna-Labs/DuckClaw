"""Resolve per-chat knowledge scope for admin playground."""

from __future__ import annotations

from duckclaw.knowledge_scope import default_knowledge_scope_for_project, normalize_knowledge_scope
from duckclaw.runtime_session_settings import resolve_session_runtime_setting


def resolve_playground_knowledge_scope(
    db: object | None,
    *,
    chat_id: str,
    tenant_id: str,
    project_id: str,
    body_scope: str | None = None,
) -> str:
    stored = ""
    if db is not None and chat_id:
        stored = resolve_session_runtime_setting(
            db,
            chat_id,
            "knowledge_scope",
            tenant_id=tenant_id,
            default="",
        )
    raw = (body_scope or stored or default_knowledge_scope_for_project(project_id)).strip()
    return normalize_knowledge_scope(raw, project_id=project_id)
