"""Tool bridge: búsqueda RAG en admin_knowledge_* vía knowledge_core."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool

from duckclaw.forge.skills.knowledge_tool_copy import SEARCH_PROJECT_KNOWLEDGE_DESCRIPTION

_EXCERPT_MAX_CHARS = 240


def _resolve_hub_db_path() -> str:
    from duckclaw.gateway_db import get_gateway_db_path, get_session_db_path

    for resolver in (get_session_db_path, get_gateway_db_path):
        path = (resolver() or "").strip()
        if path:
            return path
    return ""


def _open_hub_db() -> Any:
    path = _resolve_hub_db_path()
    if not path:
        raise RuntimeError("No hay ruta DuckDB del gateway disponible para búsqueda RAG.")
    try:
        from duckclaw.forge.skills.report_engine_hub_context import get_report_engine_hub_db
        from duckclaw.state_delta_vault import _same_vault_db_path

        reuse = get_report_engine_hub_db()
        if reuse is not None:
            rpath = str(getattr(reuse, "_path", "") or "").strip()
            if rpath and _same_vault_db_path(rpath, path):
                return reuse
    except Exception:
        pass
    from duckclaw import DuckClaw

    return DuckClaw(path, read_only=True)


def _format_excerpt(text: str) -> str:
    raw = (text or "").strip()
    if len(raw) <= _EXCERPT_MAX_CHARS:
        return raw
    return raw[: _EXCERPT_MAX_CHARS - 1].rstrip() + "…"


def search_project_knowledge(query: str, source_id: str = "") -> str:
    """Busca fragmentos RAG en admin_knowledge_* según el alcance activo."""
    from duckclaw.forge.rag.knowledge_core import search_knowledge
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

    q = (query or "").strip()
    if not q:
        return json.dumps({"error": "La consulta de búsqueda está vacía."}, ensure_ascii=False)

    db = None
    try:
        db = _open_hub_db()
        rows = search_knowledge(
            db,
            query=q,
            tenant_id=get_knowledge_tool_tenant_id(),
            project_id=project_id,
            worker_uid=get_knowledge_tool_worker_uid(),
            source_id=(source_id or "").strip(),
            knowledge_scope=scope,
        )
        if not rows:
            from duckclaw.forge.rag.knowledge_core import read_knowledge_document

            rows = read_knowledge_document(
                db,
                relative_path=q,
                tenant_id=get_knowledge_tool_tenant_id(),
                project_id=project_id,
                worker_uid=get_knowledge_tool_worker_uid(),
                knowledge_scope=scope,
                limit=8,
            )
        chunks = [
            {
                "relative_path": str(row.get("relative_path") or ""),
                "chunk_index": int(row.get("chunk_index") or 0),
                "score": row.get("score"),
                "excerpt": _format_excerpt(str(row.get("text") or "")),
            }
            for row in rows
        ]
        return json.dumps({"chunks": chunks}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def register_search_project_knowledge_tool(tools_list: list[Any]) -> None:
    tools_list.append(
        StructuredTool.from_function(
            search_project_knowledge,
            name="search_project_knowledge",
            description=SEARCH_PROJECT_KNOWLEDGE_DESCRIPTION,
        )
    )
