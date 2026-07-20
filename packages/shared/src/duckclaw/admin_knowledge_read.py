"""Read-model queries for admin knowledge / RAG sources.

Owner module for SELECTs against ``main.admin_knowledge_*`` used by the admin
gateway and other read-only callers. Mutations stay in typed write commands.

Spec: docs/architecture/DB_FIRST_CORE_REFACTOR.md
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


def _fetchone(result: Any) -> Any | None:
    if hasattr(result, "fetchone"):
        return result.fetchone()
    rows = _fetchall(result)
    return rows[0] if rows else None


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
        document_paths,
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
        "document_paths": str(document_paths or ""),
    }


def list_knowledge_sources(
    db: Any,
    *,
    tenant_id: str,
    project_id: str = "",
    worker_uid: str = "",
    knowledge_scope: str = "",
) -> list[dict[str, Any]]:
    """List active knowledge sources for a tenant with document/chunk counts."""
    from duckclaw.knowledge_scope import default_knowledge_scope_for_project, normalize_knowledge_scope

    scope = normalize_knowledge_scope(
        knowledge_scope or default_knowledge_scope_for_project(project_id),
        project_id=project_id,
    )
    clauses = ["s.tenant_id = ?", "s.active = true"]
    params: list[Any] = [tenant_id]
    if scope == "platform":
        clauses.append("(s.project_id = '' OR s.project_id IS NULL)")
    elif scope == "project":
        clauses.append("s.project_id = ?")
        params.append(project_id)
    elif project_id:
        clauses.append("(s.project_id = ? OR s.project_id = '' OR s.project_id IS NULL)")
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
                   COUNT(DISTINCT c.chunk_id) AS chunk_count,
                   COALESCE(
                     string_agg(DISTINCT d.relative_path, ', ' ORDER BY d.relative_path),
                     ''
                   ) AS document_paths
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


def get_knowledge_source(
    db: Any,
    *,
    tenant_id: str,
    source_id: str,
) -> dict[str, Any] | None:
    """Return one active knowledge source for a tenant, or None."""
    row = _fetchone(
        db.execute(
        """
        SELECT s.source_id, s.tenant_id, s.project_id, s.worker_uid, s.source_kind,
               s.source_uri, s.display_name, s.status, s.metadata_json, s.active,
               s.created_at, s.updated_at,
               COUNT(DISTINCT d.document_id) AS document_count,
               COUNT(DISTINCT c.chunk_id) AS chunk_count,
               COALESCE(
                 string_agg(DISTINCT d.relative_path, ', ' ORDER BY d.relative_path),
                 ''
               ) AS document_paths
        FROM main.admin_knowledge_sources s
        LEFT JOIN main.admin_knowledge_documents d
          ON d.source_id = s.source_id AND d.active = true
        LEFT JOIN main.admin_knowledge_chunks c
          ON c.source_id = s.source_id AND c.active = true
        WHERE s.source_id = ? AND s.tenant_id = ? AND s.active = true
        GROUP BY s.source_id, s.tenant_id, s.project_id, s.worker_uid, s.source_kind,
                 s.source_uri, s.display_name, s.status, s.metadata_json, s.active,
                 s.created_at, s.updated_at
        """,
        [source_id, tenant_id],
        )
    )
    if not row:
        return None
    return _knowledge_source_row(tuple(row))


def list_source_document_checksums(
    db: Any,
    *,
    source_id: str,
) -> dict[str, tuple[str, str, int]]:
    """Map relative_path -> (document_id, checksum, byte_size) for active documents."""
    rows = _fetchall(
        db.execute(
            """
            SELECT relative_path, document_id, checksum, byte_size
            FROM main.admin_knowledge_documents
            WHERE source_id = ? AND active = true
            """,
            [source_id],
        )
    )
    out: dict[str, tuple[str, str, int]] = {}
    for relative_path, document_id, checksum, byte_size in rows:
        rel = str(relative_path or "").strip()
        if not rel:
            continue
        out[rel] = (str(document_id), str(checksum or ""), int(byte_size or 0))
    return out


def list_folder_knowledge_sources(
    db: Any,
    *,
    tenant_id: str = "",
    project_id: str = "",
) -> list[dict[str, Any]]:
    """Active folder sources with local server paths (for auto-sync)."""
    clauses = [
        "s.active = true",
        "s.source_kind = 'folder'",
        "s.source_uri NOT LIKE 'upload://%'",
    ]
    params: list[Any] = []
    if tenant_id:
        clauses.append("s.tenant_id = ?")
        params.append(tenant_id)
    if project_id:
        clauses.append("(s.project_id = ? OR s.project_id = '')")
        params.append(project_id)
    rows = _fetchall(
        db.execute(
            f"""
            SELECT s.source_id, s.tenant_id, s.project_id, s.worker_uid, s.source_kind,
                   s.source_uri, s.display_name, s.status, s.metadata_json
            FROM main.admin_knowledge_sources s
            WHERE {' AND '.join(clauses)}
            ORDER BY s.updated_at DESC
            """,
            params,
        )
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        (
            source_id,
            tid,
            pid,
            worker_uid,
            source_kind,
            source_uri,
            display_name,
            status,
            metadata_json,
        ) = row
        try:
            metadata = json.loads(metadata_json or "{}")
        except json.JSONDecodeError:
            metadata = {}
        out.append(
            {
                "source_id": str(source_id),
                "tenant_id": str(tid or ""),
                "project_id": str(pid or ""),
                "worker_uid": str(worker_uid or ""),
                "source_kind": str(source_kind or ""),
                "source_uri": str(source_uri or ""),
                "display_name": str(display_name or ""),
                "status": str(status or ""),
                "metadata": metadata,
            }
        )
    return out


def list_project_knowledge_documents(
    db: Any,
    *,
    tenant_id: str,
    project_id: str,
    worker_uid: str = "",
    knowledge_scope: str = "both",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List active RAG documents for a scope (for agent inventory tool)."""
    from duckclaw.knowledge_scope import build_knowledge_scope_clauses, normalize_knowledge_scope, scope_allows_retrieval

    scope = normalize_knowledge_scope(knowledge_scope, project_id=project_id)
    if not scope_allows_retrieval(scope, project_id=project_id):
        return []
    scope_clauses, scope_params = build_knowledge_scope_clauses(
        knowledge_scope=scope,
        project_id=project_id,
        source_alias="s",
        chunk_alias="c",
    )
    clauses = [
        "s.tenant_id = ?",
        "s.active = true",
        "d.active = true",
        *scope_clauses,
    ]
    params: list[Any] = [tenant_id, *scope_params]
    if worker_uid:
        clauses.append("(s.worker_uid = ? OR s.worker_uid = '')")
        params.append(worker_uid)
    lim = max(1, min(int(limit), 200))
    rows = _fetchall(
        db.execute(
            f"""
            SELECT d.relative_path, d.title, s.display_name, s.source_id,
                   COUNT(DISTINCT c.chunk_id) AS chunk_count
            FROM main.admin_knowledge_documents d
            JOIN main.admin_knowledge_sources s ON s.source_id = d.source_id
            LEFT JOIN main.admin_knowledge_chunks c
              ON c.document_id = d.document_id AND c.active = true
            WHERE {' AND '.join(clauses)}
            GROUP BY d.relative_path, d.title, s.display_name, s.source_id, d.document_id
            ORDER BY d.relative_path ASC
            LIMIT {lim}
            """,
            params,
        )
    )
    return [
        {
            "relative_path": str(relative_path or ""),
            "title": str(title or ""),
            "source": str(display_name or source_id or ""),
            "chunk_count": int(chunk_count or 0),
        }
        for relative_path, title, display_name, source_id, chunk_count in rows
    ]
