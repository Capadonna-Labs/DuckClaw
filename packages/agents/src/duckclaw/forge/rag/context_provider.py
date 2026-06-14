"""Project-scoped RAG context blocks for agent prompts.

This module is intentionally framework-agnostic: callers provide a DuckDB
connection and receive structured inventory plus prompt blocks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from duckclaw.forge.rag.knowledge_core import search_knowledge

RAG_GUIDANCE_LINE = (
    "No confundas la base de conocimiento RAG con la bóveda DuckDB; "
    "DuckDB es almacenamiento interno."
)


@dataclass(frozen=True)
class KnowledgeContext:
    inventory: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    inventory_block: str
    rag_block: str
    guidance_line: str = RAG_GUIDANCE_LINE

    @property
    def context_count(self) -> int:
        return len(self.rows)


def knowledge_inventory_for_project(
    db: Any,
    *,
    tenant_id: str,
    project_id: str,
    worker_uid: str = "",
    limit: int = 8,
) -> list[dict[str, Any]]:
    if not project_id:
        return []
    clauses = ["s.tenant_id = ?", "s.active = true", "(s.project_id = ? OR s.project_id = '')"]
    params: list[Any] = [tenant_id, project_id]
    if worker_uid:
        clauses.append("(s.worker_uid = ? OR s.worker_uid = '')")
        params.append(worker_uid)
    try:
        rows = db.execute(
            f"""
            SELECT s.source_id, s.display_name, s.source_kind, s.source_uri, s.status,
                   COUNT(DISTINCT d.document_id) AS document_count,
                   COUNT(DISTINCT c.chunk_id) AS chunk_count,
                   MAX(s.updated_at) AS last_updated_at
            FROM main.admin_knowledge_sources s
            LEFT JOIN main.admin_knowledge_documents d
              ON d.source_id = s.source_id AND d.active = true
            LEFT JOIN main.admin_knowledge_chunks c
              ON c.source_id = s.source_id AND c.active = true
            WHERE {' AND '.join(clauses)}
            GROUP BY s.source_id, s.display_name, s.source_kind, s.source_uri, s.status
            ORDER BY last_updated_at DESC
            LIMIT {max(1, min(int(limit), 20))}
            """,
            params,
        )
        if hasattr(rows, "fetchall"):
            rows = rows.fetchall()
    except Exception:
        return []
    inventory = [
        {
            "source_id": str(row[0] or ""),
            "display_name": str(row[1] or row[3] or "Fuente RAG"),
            "source_kind": str(row[2] or ""),
            "source_uri": str(row[3] or ""),
            "status": str(row[4] or ""),
            "document_count": int(row[5] or 0),
            "chunk_count": int(row[6] or 0),
        }
        for row in rows
    ]
    return inventory


def build_knowledge_context(
    db: Any,
    *,
    query: str,
    tenant_id: str,
    project_id: str,
    worker_uid: str = "",
    inventory_limit: int = 8,
    retrieval_limit: int = 6,
    embedding_fn: Callable[[str], list[float] | None] | None = None,
) -> KnowledgeContext:
    inventory = knowledge_inventory_for_project(
        db,
        tenant_id=tenant_id,
        project_id=project_id,
        worker_uid=worker_uid,
        limit=inventory_limit,
    )
    rows = search_knowledge(
        db,
        query=query,
        tenant_id=tenant_id,
        project_id=project_id,
        worker_uid=worker_uid,
        limit=retrieval_limit,
        embedding_fn=embedding_fn,
    )
    context = KnowledgeContext(
        inventory=inventory,
        rows=rows,
        inventory_block=format_inventory_block(inventory),
        rag_block=format_rag_block(rows),
    )
    return context


def format_inventory_block(inventory: list[dict[str, Any]]) -> str:
    if not inventory:
        return ""
    lines = [
        f"- {source['display_name']} ({source['status']}): "
        f"{source['document_count']} docs, {source['chunk_count']} chunks, tipo={source['source_kind']}"
        for source in inventory
    ]
    return "\n".join(["[RAG_SOURCE_INVENTORY]", *lines, "[/RAG_SOURCE_INVENTORY]"])


def format_rag_block(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    lines: list[str] = []
    for index, row in enumerate(rows, start=1):
        text = re.sub(r"\s+", " ", str(row.get("text") or "")).strip()[:1200]
        path = str(row.get("relative_path") or row.get("source_id") or "fuente")
        chunk_index = row.get("chunk_index")
        lines.extend([f"[{index}] {path}#chunk-{chunk_index}", text, ""])
    return "\n".join(["[RAG_CONTEXT]", *lines, "[/RAG_CONTEXT]"])
