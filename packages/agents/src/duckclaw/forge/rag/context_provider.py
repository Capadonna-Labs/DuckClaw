"""Project-scoped RAG context blocks for agent prompts.

This module is intentionally framework-agnostic: callers provide a DuckDB
connection and receive structured inventory plus prompt blocks.
"""

from __future__ import annotations

import re
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from duckclaw.forge.rag.knowledge_core import search_knowledge

RAG_GUIDANCE_LINE = (
    "No confundas la base de conocimiento RAG con la bóveda DuckDB; "
    "DuckDB es almacenamiento interno."
)
_DEBUG_LOG_PATH = Path("/Users/workstation/Developer/duckclaw/.cursor/debug-ab0734.log")


def _agent_debug_log(hypothesis_id: str, message: str, data: dict[str, Any]) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": "ab0734",
            "runId": "initial-rag-debug",
            "hypothesisId": hypothesis_id,
            "location": "packages/agents/src/duckclaw/forge/rag/context_provider.py",
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        _DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass
    # endregion


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
    except Exception as exc:
        _agent_debug_log(
            "H3",
            "knowledge inventory query failed",
            {
                "project_id_present": bool(project_id),
                "worker_uid_present": bool(worker_uid),
                "error_type": type(exc).__name__,
                "error": str(exc)[:200],
            },
        )
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
    _agent_debug_log(
        "H3",
        "knowledge inventory query completed",
        {
            "project_id_present": bool(project_id),
            "worker_uid_present": bool(worker_uid),
            "inventory_count": len(inventory),
            "document_total": sum(int(item.get("document_count") or 0) for item in inventory),
            "chunk_total": sum(int(item.get("chunk_count") or 0) for item in inventory),
        },
    )
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
    _agent_debug_log(
        "H3,H4",
        "knowledge context built",
        {
            "query_len": len(query or ""),
            "project_id_present": bool(project_id),
            "worker_uid_present": bool(worker_uid),
            "inventory_count": len(context.inventory),
            "retrieval_rows": len(context.rows),
            "has_inventory_block": bool(context.inventory_block),
            "has_rag_block": bool(context.rag_block),
        },
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
