"""Tool bridge: leer documento RAG completo por ruta relativa."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool

from duckclaw.forge.skills.knowledge_tool_copy import READ_PROJECT_KNOWLEDGE_DESCRIPTION
from duckclaw.forge.skills.search_project_knowledge_bridge import _open_hub_db

_READ_MAX_CHARS = 12000


def read_project_knowledge(relative_path: str) -> str:
    """Lee chunks de un documento RAG por ruta (ej. IngenieroSoftware/Cache.md)."""
    from duckclaw.forge.rag.knowledge_core import read_knowledge_document
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
            },
            ensure_ascii=False,
        )

    path = (relative_path or "").strip()
    if not path:
        return json.dumps({"error": "Indica relative_path del documento."}, ensure_ascii=False)

    db = None
    try:
        db = _open_hub_db()
        rows = read_knowledge_document(
            db,
            relative_path=path,
            tenant_id=get_knowledge_tool_tenant_id(),
            project_id=project_id,
            worker_uid=get_knowledge_tool_worker_uid(),
            knowledge_scope=scope,
        )
        if not rows:
            return json.dumps(
                {"error": f"No se encontró documento indexado que coincida con: {path}"},
                ensure_ascii=False,
            )
        resolved_path = str(rows[0].get("relative_path") or path)
        parts: list[str] = []
        total = 0
        for row in rows:
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            if total + len(text) > _READ_MAX_CHARS:
                parts.append(text[: max(0, _READ_MAX_CHARS - total)] + "…")
                break
            parts.append(text)
            total += len(text)
        return json.dumps(
            {
                "relative_path": resolved_path,
                "chunk_count": len(rows),
                "content": "\n\n".join(parts),
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


def register_read_project_knowledge_tool(tools_list: list[Any]) -> None:
    tools_list.append(
        StructuredTool.from_function(
            read_project_knowledge,
            name="read_project_knowledge",
            description=READ_PROJECT_KNOWLEDGE_DESCRIPTION,
        )
    )
