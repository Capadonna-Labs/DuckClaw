"""Contexto de proyecto y RAG para turnos de admin playground."""

from __future__ import annotations

from typing import Any


def project_context_message(
    *,
    msg: str,
    project_context: dict[str, Any],
    worker_id: str,
    tenant_id: str,
    project_id: str,
) -> tuple[str, int]:
    from core.admin_identity import open_gateway_db

    agent_ids = [
        str(agent.get("worker_id") or "").strip()
        for agent in project_context.get("agents", [])
        if str(agent.get("worker_id") or "").strip()
    ]
    worker_uid = next(
        (
            str(agent.get("worker_uid") or "").strip()
            for agent in project_context.get("agents", [])
            if str(agent.get("worker_id") or "").strip() == worker_id
        ),
        "",
    )
    knowledge_blocks: list[str] = []
    rag_context_count = 0
    try:
        from duckclaw.forge.rag.context_provider import build_knowledge_context

        with open_gateway_db(read_only=True) as db:
            knowledge_context = build_knowledge_context(
                db,
                query=msg,
                tenant_id=tenant_id,
                project_id=project_id,
                worker_uid=worker_uid,
            )
        rag_context_count = knowledge_context.context_count
        if knowledge_context.inventory_block:
            knowledge_blocks.append(knowledge_context.inventory_block)
        if knowledge_context.rag_block:
            knowledge_blocks.append(knowledge_context.rag_block)
    except Exception:
        rag_context_count = 0
        knowledge_blocks = []
    project_block = "\n".join(
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
    return "\n\n".join([project_block, *knowledge_blocks, msg]), rag_context_count
