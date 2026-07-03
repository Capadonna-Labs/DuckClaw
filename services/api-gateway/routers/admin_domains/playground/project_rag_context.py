"""Contexto de proyecto y RAG para turnos de admin playground."""

from __future__ import annotations

from typing import Any


def _worker_uid_for_project(
    project_context: dict[str, Any] | None,
    worker_id: str,
) -> str:
    if not project_context:
        return ""
    return next(
        (
            str(agent.get("worker_uid") or "").strip()
            for agent in project_context.get("agents", [])
            if str(agent.get("worker_id") or "").strip() == worker_id
        ),
        "",
    )


def project_context_message(
    *,
    msg: str,
    project_context: dict[str, Any] | None,
    worker_id: str,
    tenant_id: str,
    project_id: str,
    knowledge_scope: str = "both",
) -> tuple[str, int]:
    from core.admin_identity import open_gateway_db
    from duckclaw.forge.rag.injection_policy import should_inject_playground_context
    from duckclaw.knowledge_scope import SCOPE_LABELS_ES, normalize_knowledge_scope, scope_allows_retrieval

    scope = normalize_knowledge_scope(knowledge_scope, project_id=project_id)
    worker_uid = _worker_uid_for_project(project_context, worker_id)
    knowledge_blocks: list[str] = []
    rag_context_count = 0

    if scope_allows_retrieval(scope, project_id=project_id) and should_inject_playground_context(msg):
        try:
            from duckclaw.forge.rag.context_provider import build_knowledge_context

            with open_gateway_db(read_only=True) as db:
                knowledge_context = build_knowledge_context(
                    db,
                    query=msg,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    worker_uid=worker_uid,
                    knowledge_scope=scope,
                )
            rag_context_count = knowledge_context.context_count
            if knowledge_context.inventory_block:
                knowledge_blocks.append(knowledge_context.inventory_block)
            if knowledge_context.rag_block:
                knowledge_blocks.append(knowledge_context.rag_block)
        except Exception:
            rag_context_count = 0
            knowledge_blocks = []

    if not should_inject_playground_context(msg):
        return msg, rag_context_count

    blocks: list[str] = []
    if project_context and project_id:
        agent_ids = [
            str(agent.get("worker_id") or "").strip()
            for agent in project_context.get("agents", [])
            if str(agent.get("worker_id") or "").strip()
        ]
        blocks.append(
            "\n".join(
                [
                    "[PROJECT_CONTEXT]",
                    f"Nombre: {project_context.get('name') or ''}",
                    f"Descripción: {project_context.get('description') or ''}",
                    f"Agentes activos: {', '.join(agent_ids) if agent_ids else 'ninguno'}",
                    "Usa el conocimiento recuperado para responder la pregunta del usuario antes de hablar de configuración interna.",
                    "Usa esta descripción solo para orientar al usuario, proponer próximos pasos y pedir datos faltantes.",
                    "[/PROJECT_CONTEXT]",
                ]
            )
        )
    elif scope_allows_retrieval(scope, project_id=project_id):
        blocks.append(
            "\n".join(
                [
                    "[KNOWLEDGE_SCOPE]",
                    f"Alcance RAG: {SCOPE_LABELS_ES.get(scope, scope)}",
                    "Usa el conocimiento recuperado para responder antes de hablar de configuración interna.",
                    "[/KNOWLEDGE_SCOPE]",
                ]
            )
        )

    return "\n\n".join([*blocks, *knowledge_blocks, msg]), rag_context_count
