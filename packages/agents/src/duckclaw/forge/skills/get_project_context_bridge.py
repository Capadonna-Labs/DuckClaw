"""Tool bridge: resumen del proyecto activo (RAG, fuentes, agente)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool

from duckclaw.forge.skills.search_project_knowledge_bridge import _open_hub_db


def get_project_context() -> str:
    """Devuelve project_id, nombre, fuentes RAG y totales del turno actual."""
    from duckclaw.admin_knowledge_read import list_knowledge_sources
    from duckclaw.forge.skills.knowledge_tool_context import (
        get_knowledge_tool_project_id,
        get_knowledge_tool_tenant_id,
        get_knowledge_tool_worker_uid,
    )

    project_id = get_knowledge_tool_project_id()
    tenant_id = get_knowledge_tool_tenant_id()
    worker_uid = get_knowledge_tool_worker_uid()

    if not project_id:
        return json.dumps(
            {
                "project_id": "",
                "tenant_id": tenant_id,
                "worker_uid": worker_uid,
                "warning": "No hay proyecto en esta conversación. Elige uno en Run settings → Proyecto.",
                "source_count": 0,
                "chunk_count": 0,
            },
            ensure_ascii=False,
        )

    db = None
    try:
        db = _open_hub_db()
        name = project_id
        try:
            row = db.execute(
                "SELECT name, status FROM main.admin_projects WHERE project_id = ? AND tenant_id = ? LIMIT 1",
                [project_id, tenant_id],
            ).fetchone()
            if row and row[0]:
                name = str(row[0])
        except Exception:
            pass

        sources = list_knowledge_sources(
            db,
            tenant_id=tenant_id,
            project_id=project_id,
            worker_uid=worker_uid,
        )
        chunk_total = sum(int(s.get("chunk_count") or 0) for s in sources)
        doc_total = sum(int(s.get("document_count") or 0) for s in sources)
        ready = sum(
            1
            for s in sources
            if str(s.get("status") or "").lower() in {"ready", "active", "done"}
            and int(s.get("chunk_count") or 0) > 0
        )

        summary_sources = [
            {
                "display_name": s.get("display_name") or s.get("source_id"),
                "source_kind": s.get("source_kind"),
                "status": s.get("status"),
                "document_count": int(s.get("document_count") or 0),
                "chunk_count": int(s.get("chunk_count") or 0),
            }
            for s in sources[:12]
        ]

        payload: dict[str, Any] = {
            "project_id": project_id,
            "project_name": name,
            "tenant_id": tenant_id,
            "worker_uid": worker_uid,
            "source_count": len(sources),
            "sources_ready_with_chunks": ready,
            "document_count": doc_total,
            "chunk_count": chunk_total,
            "sources_preview": summary_sources,
        }
        if chunk_total == 0 and len(sources) > 0:
            payload["warning"] = (
                "Hay fuentes registradas pero 0 fragmentos indexados; RAG no inyectará contenido hasta indexar."
            )
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc), "project_id": project_id}, ensure_ascii=False)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def register_get_project_context_tool(tools_list: list[Any]) -> None:
    tools_list.append(
        StructuredTool.from_function(
            get_project_context,
            name="get_project_context",
            description=(
                "Resumen del proyecto activo: nombre, fuentes RAG, fragmentos indexados y avisos. "
                "Úsalo al inicio si necesitas saber si hay conocimiento disponible o falta elegir proyecto."
            ),
        )
    )
