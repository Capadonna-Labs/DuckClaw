"""Knowledge retrieval scope: platform (framework), project, or both."""

from __future__ import annotations

from typing import Any, Literal

KnowledgeScope = Literal["platform", "project", "both"]

VALID_KNOWLEDGE_SCOPES: frozenset[str] = frozenset({"platform", "project", "both"})

SCOPE_LABELS_ES: dict[str, str] = {
    "platform": "Plataforma",
    "project": "Proyecto",
    "both": "Plataforma + proyecto",
}


def normalize_knowledge_scope(
    raw: str | None,
    *,
    project_id: str = "",
) -> KnowledgeScope:
    """Resolve a valid scope; downgrade when project context is missing."""
    scope = (raw or "").strip().lower()
    pid = (project_id or "").strip()
    if scope not in VALID_KNOWLEDGE_SCOPES:
        scope = "both" if pid else "platform"
    if scope == "project" and not pid:
        return "platform"
    if scope == "both" and not pid:
        return "platform"
    return scope  # type: ignore[return-value]


def default_knowledge_scope_for_project(project_id: str) -> KnowledgeScope:
    pid = (project_id or "").strip()
    return "both" if pid else "platform"


def scope_allows_retrieval(scope: str, *, project_id: str = "") -> bool:
    normalized = normalize_knowledge_scope(scope, project_id=project_id)
    if normalized == "platform":
        return True
    return bool((project_id or "").strip())


def build_knowledge_scope_clauses(
    *,
    knowledge_scope: str,
    project_id: str,
    source_alias: str = "s",
    chunk_alias: str = "c",
) -> tuple[list[str], list[Any]]:
    """SQL fragments for admin_knowledge_* scope filtering."""
    scope = normalize_knowledge_scope(knowledge_scope, project_id=project_id)
    pid = (project_id or "").strip()
    clauses: list[str] = []
    params: list[Any] = []

    if scope == "platform":
        clauses.append(f"({source_alias}.project_id = '' OR {source_alias}.project_id IS NULL)")
        clauses.append(f"({chunk_alias}.project_id = '' OR {chunk_alias}.project_id IS NULL)")
    elif scope == "project":
        clauses.append(f"{source_alias}.project_id = ?")
        clauses.append(f"{chunk_alias}.project_id = ?")
        params.extend([pid, pid])
    else:
        if pid:
            clauses.append(
                f"({chunk_alias}.project_id = ? OR {chunk_alias}.project_id = '' OR {chunk_alias}.project_id IS NULL)"
            )
            params.append(pid)
            clauses.append(
                f"({source_alias}.project_id = ? OR {source_alias}.project_id = '' OR {source_alias}.project_id IS NULL)"
            )
            params.append(pid)
        else:
            clauses.append(f"({source_alias}.project_id = '' OR {source_alias}.project_id IS NULL)")
            clauses.append(f"({chunk_alias}.project_id = '' OR {chunk_alias}.project_id IS NULL)")
    return clauses, params


__all__ = [
    "KnowledgeScope",
    "SCOPE_LABELS_ES",
    "VALID_KNOWLEDGE_SCOPES",
    "build_knowledge_scope_clauses",
    "default_knowledge_scope_for_project",
    "normalize_knowledge_scope",
    "scope_allows_retrieval",
]
