"""Tool bridge: resumen del proyecto activo (RAG, fuentes, agente)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool

from duckclaw.forge.skills.knowledge_tool_copy import GET_PROJECT_CONTEXT_DESCRIPTION
from duckclaw.forge.skills.search_project_knowledge_bridge import _open_hub_db


def _disk_allowed_roots_preview() -> list[dict[str, Any]]:
    """Raíces de disco (ALLOWED_ROOTS); no son fuentes RAG hasta indexar."""
    try:
        from duckclaw.forge.rag.knowledge_paths import knowledge_allowed_roots
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for root in knowledge_allowed_roots():
        try:
            exists = root.exists()
        except OSError:
            exists = False
        rows.append(
            {
                "label": root.name or str(root),
                "path": str(root),
                "exists": exists,
                "in_chat": False,
                "note": "Solo disco hasta «Añadir al chat» en Conocimiento",
            }
        )
    return rows[:16]


def get_project_context() -> str:
    """Devuelve alcance RAG, proyecto, fuentes indexadas y raíces de disco."""
    from duckclaw.admin_knowledge_read import list_knowledge_sources
    from duckclaw.forge.skills.knowledge_tool_context import (
        get_knowledge_tool_project_id,
        get_knowledge_tool_scope,
        get_knowledge_tool_tenant_id,
        get_knowledge_tool_worker_uid,
    )
    from duckclaw.knowledge_scope import SCOPE_LABELS_ES, normalize_knowledge_scope, scope_allows_retrieval

    project_id = get_knowledge_tool_project_id()
    tenant_id = get_knowledge_tool_tenant_id()
    worker_uid = get_knowledge_tool_worker_uid()
    scope = normalize_knowledge_scope(get_knowledge_tool_scope(), project_id=project_id)
    disk_roots = _disk_allowed_roots_preview()

    if not scope_allows_retrieval(scope, project_id=project_id):
        return json.dumps(
            {
                "project_id": project_id or "",
                "knowledge_scope": scope,
                "knowledge_scope_label": SCOPE_LABELS_ES.get(scope, scope),
                "tenant_id": tenant_id,
                "worker_uid": worker_uid,
                "warning": (
                    "Alcance «Proyecto» requiere elegir un proyecto en Run settings, "
                    "o cambia a Plataforma / Plataforma + proyecto."
                ),
                "source_count": 0,
                "chunk_count": 0,
                "disk_allowed_roots": disk_roots,
                "lanes": {
                    "in_chat": "Fuentes indexadas → search/list/read_project_knowledge",
                    "on_disk": (
                        "Raíces permitidas → list_disk_roots / list_disk_folder / "
                        "read_disk_text / extract_document_text (no RAG)"
                    ),
                },
            },
            ensure_ascii=False,
        )

    db = None
    try:
        db = _open_hub_db()
        name = project_id or SCOPE_LABELS_ES.get(scope, "Plataforma")
        if project_id:
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
            knowledge_scope=scope,
        )
        chunk_total = sum(int(s.get("chunk_count") or 0) for s in sources)
        doc_total = sum(int(s.get("document_count") or 0) for s in sources)
        ready = sum(
            1
            for s in sources
            if str(s.get("status") or "").lower() in {"ready", "active", "done"}
            and int(s.get("chunk_count") or 0) > 0
        )

        indexed_uris = {
            str(s.get("source_uri") or "").rstrip("/").lower()
            for s in sources
            if str(s.get("source_uri") or "").strip()
        }
        for row in disk_roots:
            path_key = str(row.get("path") or "").rstrip("/").lower()
            if path_key and path_key in indexed_uris:
                row["in_chat"] = True
                row["note"] = "También indexada en el chat"

        summary_sources = [
            {
                "display_name": s.get("display_name") or s.get("source_id"),
                "source_kind": s.get("source_kind"),
                "status": s.get("status"),
                "project_id": s.get("project_id") or "",
                "document_count": int(s.get("document_count") or 0),
                "chunk_count": int(s.get("chunk_count") or 0),
                "source_uri": s.get("source_uri") or "",
            }
            for s in sources[:12]
        ]

        payload: dict[str, Any] = {
            "project_id": project_id or "",
            "project_name": name,
            "knowledge_scope": scope,
            "knowledge_scope_label": SCOPE_LABELS_ES.get(scope, scope),
            "tenant_id": tenant_id,
            "worker_uid": worker_uid,
            "source_count": len(sources),
            "sources_ready_with_chunks": ready,
            "document_count": doc_total,
            "chunk_count": chunk_total,
            "sources_preview": summary_sources,
            "disk_allowed_roots": disk_roots,
            "lanes": {
                "in_chat": "Fuentes indexadas → search/list/read_project_knowledge",
                "on_disk": (
                    "Raíces permitidas → list_disk_roots / list_disk_folder / "
                    "read_disk_text / extract_document_text; no búsqueda semántica"
                ),
            },
        }
        if chunk_total == 0 and len(sources) > 0:
            payload["warning"] = (
                "Hay fuentes registradas pero 0 fragmentos indexados; RAG no inyectará contenido hasta indexar."
            )
        elif chunk_total == 0:
            payload["warning"] = (
                "No hay conocimiento indexado en el chat para este alcance. "
                "Las carpetas en disk_allowed_roots existen en disco pero no se buscan con RAG "
                "hasta «Añadir al chat» en Conocimiento."
            )
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        return json.dumps(
            {
                "error": str(exc),
                "project_id": project_id,
                "disk_allowed_roots": disk_roots,
            },
            ensure_ascii=False,
        )
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
            description=GET_PROJECT_CONTEXT_DESCRIPTION,
        )
    )
