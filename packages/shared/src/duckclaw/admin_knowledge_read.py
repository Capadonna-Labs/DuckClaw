"""Read-model queries for admin knowledge / RAG sources.

Owner module for SELECTs against ``main.admin_knowledge_*`` used by the admin
gateway and other read-only callers. Mutations stay in typed write commands.

Spec: docs/specs/features/platform/RAG_TRANSVERSAL_DB_FIRST.md
"""

from __future__ import annotations

import json
from typing import Any


def _fetchall(result: Any) -> list[Any]:
    if hasattr(result, "fetchall"):
        return list(result.fetchall())
    if isinstance(result, list):
        return result
    return []


def _knowledge_source_row(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        source_id,
        tenant_id,
        project_id,
        worker_uid,
        source_kind,
        source_uri,
        display_name,
        status,
        metadata_json,
        active,
        created_at,
        updated_at,
        document_count,
        chunk_count,
    ) = row
    try:
        metadata = json.loads(metadata_json or "{}")
    except json.JSONDecodeError:
        metadata = {}
    return {
        "source_id": str(source_id),
        "tenant_id": str(tenant_id or ""),
        "project_id": str(project_id or ""),
        "worker_uid": str(worker_uid or ""),
        "source_kind": str(source_kind or ""),
        "source_uri": str(source_uri or ""),
        "display_name": str(display_name or ""),
        "status": str(status or ""),
        "metadata": metadata,
        "active": bool(active),
        "created_at": str(created_at),
        "updated_at": str(updated_at),
        "document_count": int(document_count or 0),
        "chunk_count": int(chunk_count or 0),
    }


def list_knowledge_sources(
    db: Any,
    *,
    tenant_id: str,
    project_id: str = "",
    worker_uid: str = "",
) -> list[dict[str, Any]]:
    """List active knowledge sources for a tenant with document/chunk counts."""
    clauses = ["s.tenant_id = ?", "s.active = true"]
    params: list[Any] = [tenant_id]
    if project_id:
        clauses.append("(s.project_id = ? OR s.project_id = '')")
        params.append(project_id)
    if worker_uid:
        clauses.append("(s.worker_uid = ? OR s.worker_uid = '')")
        params.append(worker_uid)
    rows = _fetchall(
        db.execute(
            f"""
            SELECT s.source_id, s.tenant_id, s.project_id, s.worker_uid, s.source_kind,
                   s.source_uri, s.display_name, s.status, s.metadata_json, s.active,
                   s.created_at, s.updated_at,
                   COUNT(DISTINCT d.document_id) AS document_count,
                   COUNT(DISTINCT c.chunk_id) AS chunk_count
            FROM main.admin_knowledge_sources s
            LEFT JOIN main.admin_knowledge_documents d
              ON d.source_id = s.source_id AND d.active = true
            LEFT JOIN main.admin_knowledge_chunks c
              ON c.source_id = s.source_id
             AND c.active = true
             AND (s.project_id = '' OR c.project_id = s.project_id OR c.project_id = '')
             AND (s.worker_uid = '' OR c.worker_uid = s.worker_uid OR c.worker_uid = '')
            WHERE {' AND '.join(clauses)}
            GROUP BY s.source_id, s.tenant_id, s.project_id, s.worker_uid, s.source_kind,
                     s.source_uri, s.display_name, s.status, s.metadata_json, s.active,
                     s.created_at, s.updated_at
            ORDER BY s.updated_at DESC
            """,
            params,
        )
    )
    return [_knowledge_source_row(row) for row in rows]
