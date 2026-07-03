"""Tool bridge: inventario de documentos RAG del proyecto."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool

from duckclaw.forge.skills.search_project_knowledge_bridge import _open_hub_db


def list_project_knowledge(limit: int = 100) -> str:
    """Lista documentos RAG del alcance activo (plataforma, proyecto o ambos)."""
    from duckclaw.admin_knowledge_read import list_project_knowledge_documents
    from duckclaw.forge.skills.knowledge_tool_context import (
        get_knowledge_tool_project_id,
        get_knowledge_tool_scope,
        get_knowledge_tool_tenant_id,
        get_knowledge_tool_worker_uid,
    )
    from duckclaw.knowledge_scope import normalize_knowledge_scope, scope_allows_retrieval

    project_id = get_knowledge_tool_project_id()
    scope = normalize_knowledge_scope(get_knowledge_tool_scope(), project_id=project_id)
    if not scope_allows_retrieval(scope, project_id=project_id):
        return json.dumps(
            {
                "error": (
                    "El alcance de conocimiento requiere proyecto. "
                    "Elige uno en Run settings o cambia a Plataforma."
                ),
                "knowledge_scope": scope,
            },
            ensure_ascii=False,
        )

    db = None
    try:
        db = _open_hub_db()
        docs = list_project_knowledge_documents(
            db,
            tenant_id=get_knowledge_tool_tenant_id(),
            project_id=project_id,
            worker_uid=get_knowledge_tool_worker_uid(),
            knowledge_scope=scope,
            limit=max(1, min(int(limit), 200)),
        )
        return json.dumps(
            {
                "knowledge_scope": scope,
                "project_id": project_id or None,
                "document_count": len(docs),
                "documents": docs,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def register_list_project_knowledge_tool(tools_list: list[Any]) -> None:
    tools_list.append(
        StructuredTool.from_function(
            list_project_knowledge,
            name="list_project_knowledge",
            description=(
                "Lista documentos indexados en la base RAG del alcance activo "
                "(plataforma, proyecto o ambos). Úsalo para inventario completo."
            ),
        )
    )
