"""Execute knowledge folder sync (admin, auto-poll, post-write)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from duckclaw.forge.rag.knowledge_core import build_document_payload, embed_chunk_payloads
from duckclaw.forge.rag.knowledge_paths import path_under_any_root, validate_knowledge_ingest_root
from duckclaw.forge.rag.knowledge_sync import folder_mtime_fingerprint, plan_folder_sync
from duckclaw.write_commands import (
    CreateKnowledgeSourceCommand,
    DeactivateKnowledgeDocumentsCommand,
    UpsertKnowledgeChunksCommand,
    UpsertKnowledgeDocumentCommand,
)

_log = logging.getLogger(__name__)

_AUTO_SYNC_ACTOR = "system@knowledge-auto-sync"
_last_fingerprint: dict[str, float] = {}


@dataclass
class SyncResult:
    source_id: str
    scanned: int = 0
    upserted: int = 0
    skipped: int = 0
    removed: int = 0
    chunks: int = 0
    task_ids: list[str] = field(default_factory=list)
    skipped_reason: str = ""


def auto_sync_enabled() -> bool:
    raw = (os.environ.get("DUCKCLAW_KNOWLEDGE_AUTO_SYNC") or "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def auto_sync_poll_seconds() -> int:
    raw = (os.environ.get("DUCKCLAW_KNOWLEDGE_AUTO_SYNC_POLL_SEC") or "15").strip()
    try:
        return max(5, int(raw))
    except ValueError:
        return 15


def _enqueue_knowledge_command(command: Any) -> str:
    from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync
    from duckclaw.gateway_db import get_gateway_db_path

    task_id = enqueue_typed_command(command, db_path=get_gateway_db_path(), user_id="default")
    status = poll_task_status_sync(task_id, timeout_sec=0.5)
    if status and status.status == "failed":
        detail = status.detail or "knowledge write failed"
        raise ValueError(detail)
    return task_id


def ingest_folder_payloads(
    *,
    source_id: str,
    tenant_id: str,
    actor_email: str,
    project_id: str,
    worker_uid: str,
    compute_embeddings: bool,
    payloads: list[Any],
) -> tuple[list[str], int]:
    task_ids: list[str] = []
    chunks_total = 0
    embedding_fn = None
    if compute_embeddings:
        from duckclaw.forge.rag.embeddings import embed_text

        embedding_fn = embed_text
    for payload in payloads:
        doc_cmd = UpsertKnowledgeDocumentCommand(
            tenant_id=tenant_id,
            actor_email=actor_email,
            **payload.document,
        )
        task_ids.append(_enqueue_knowledge_command(doc_cmd))
        chunk_payloads = (
            embed_chunk_payloads(payload.chunks, embedding_fn)
            if embedding_fn is not None
            else payload.chunks
        )
        chunk_cmd = UpsertKnowledgeChunksCommand(
            tenant_id=tenant_id,
            actor_email=actor_email,
            document_id=payload.document["document_id"],
            source_id=source_id,
            project_id=project_id,
            worker_uid=worker_uid,
            chunks=chunk_payloads,
        )
        task_ids.append(_enqueue_knowledge_command(chunk_cmd))
        chunks_total += len(chunk_payloads)
    return task_ids, chunks_total


def execute_folder_sync(
    *,
    source: dict[str, Any],
    existing: dict[str, tuple[str, str]],
    actor_email: str,
    compute_embeddings: bool = True,
    force: bool = False,
) -> SyncResult:
    source_id = str(source["source_id"])
    source_uri = str(source.get("source_uri") or "").strip()
    result = SyncResult(source_id=source_id)

    if not source_uri or source_uri.startswith("upload://"):
        result.skipped_reason = "not_a_folder_uri"
        return result
    if str(source.get("source_kind") or "") != "folder":
        result.skipped_reason = "not_folder_kind"
        return result

    try:
        root = validate_knowledge_ingest_root(source_uri)
    except (ValueError, FileNotFoundError) as exc:
        result.skipped_reason = str(exc)
        return result

    fingerprint = folder_mtime_fingerprint(root)
    if not force and _last_fingerprint.get(source_id) == fingerprint:
        result.skipped_reason = "unchanged_fingerprint"
        result.scanned = len(existing)
        result.skipped = len(existing)
        return result

    plan = plan_folder_sync(root=root, source_id=source_id, existing=existing)
    if not force and not plan.to_upsert and not plan.to_deactivate:
        _last_fingerprint[source_id] = fingerprint
        result.scanned = plan.scanned
        result.skipped = plan.skipped
        result.skipped_reason = "no_changes"
        return result

    tenant_id = str(source.get("tenant_id") or "default")
    project_id = str(source.get("project_id") or "")
    worker_uid = str(source.get("worker_uid") or "")

    indexing_cmd = CreateKnowledgeSourceCommand(
        source_id=source_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
        project_id=project_id,
        worker_uid=worker_uid,
        source_kind="folder",
        source_uri=source_uri,
        display_name=str(source.get("display_name") or ""),
        status="indexing",
        metadata=dict(source.get("metadata") or {}),
    )
    result.task_ids.append(_enqueue_knowledge_command(indexing_cmd))

    if plan.to_deactivate:
        deactivate_cmd = DeactivateKnowledgeDocumentsCommand(
            tenant_id=tenant_id,
            actor_email=actor_email,
            source_id=source_id,
            document_ids=plan.to_deactivate,
        )
        result.task_ids.append(_enqueue_knowledge_command(deactivate_cmd))

    ingest_task_ids, chunks = ingest_folder_payloads(
        source_id=source_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
        project_id=project_id,
        worker_uid=worker_uid,
        compute_embeddings=compute_embeddings,
        payloads=plan.to_upsert,
    )
    result.task_ids.extend(ingest_task_ids)
    result.scanned = plan.scanned
    result.upserted = len(plan.to_upsert)
    result.skipped = plan.skipped
    result.removed = len(plan.to_deactivate)
    result.chunks = chunks

    sync_stats = {
        "scanned": result.scanned,
        "upserted": result.upserted,
        "skipped": result.skipped,
        "removed": result.removed,
        "chunks": result.chunks,
        "auto": actor_email == _AUTO_SYNC_ACTOR,
    }
    ready_cmd = CreateKnowledgeSourceCommand(
        source_id=source_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
        project_id=project_id,
        worker_uid=worker_uid,
        source_kind="folder",
        source_uri=source_uri,
        display_name=str(source.get("display_name") or ""),
        status="ready",
        metadata={
            **dict(source.get("metadata") or {}),
            "last_sync_at": datetime.now(timezone.utc).isoformat(),
            "sync_stats": sync_stats,
        },
    )
    result.task_ids.append(_enqueue_knowledge_command(ready_cmd))
    _last_fingerprint[source_id] = fingerprint
    return result


def _open_hub_db() -> Any | None:
    from duckclaw.gateway_db import get_gateway_db_path

    path = (get_gateway_db_path() or "").strip()
    if not path:
        return None
    try:
        from duckclaw.forge.skills.report_engine_hub_context import get_report_engine_hub_db
        from duckclaw.state_delta_vault import _same_vault_db_path

        reuse = get_report_engine_hub_db()
        if reuse is not None and _same_vault_db_path(str(getattr(reuse, "_path", "") or ""), path):
            return reuse
    except Exception:
        pass
    try:
        from duckclaw import DuckClaw

        return DuckClaw(path, read_only=True)
    except Exception as exc:
        msg = str(exc).lower()
        if "lock" in msg or "conflicting" in msg:
            _log.debug("knowledge auto-sync: hub db ocupado, omitiendo ciclo: %s", exc)
            return None
        raise


def _folder_sources_containing_file(
    db: Any,
    *,
    file_path: Path,
    tenant_id: str,
    project_id: str = "",
) -> list[dict[str, Any]]:
    from duckclaw.admin_knowledge_read import list_folder_knowledge_sources

    resolved = file_path.expanduser().resolve()
    sources = list_folder_knowledge_sources(db, tenant_id=tenant_id, project_id=project_id)
    matched: list[dict[str, Any]] = []
    for source in sources:
        root = Path(str(source.get("source_uri") or "")).expanduser().resolve()
        if path_under_any_root(resolved, [root]):
            matched.append(source)
    return matched


def sync_file_after_write(
    *,
    file_path: Path,
    tenant_id: str,
    project_id: str = "",
    compute_embeddings: bool = True,
) -> dict[str, Any]:
    """Re-index a single written file into matching folder sources."""
    if not auto_sync_enabled():
        return {"synced": False, "reason": "auto_sync_disabled"}

    db = _open_hub_db()
    if db is None:
        return {"synced": False, "reason": "no_hub_db"}

    results: list[dict[str, Any]] = []
    try:
        from duckclaw.admin_knowledge_read import list_source_document_checksums

        sources = _folder_sources_containing_file(
            db,
            file_path=file_path,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        if not sources:
            return {"synced": False, "reason": "no_matching_source", "sources": []}

        resolved = file_path.expanduser().resolve()
        for source in sources:
            source_id = str(source["source_id"])
            source_uri = str(source.get("source_uri") or "").strip()
            try:
                root = validate_knowledge_ingest_root(source_uri)
            except (ValueError, FileNotFoundError):
                continue
            base = root if root.is_dir() else root.parent
            if not path_under_any_root(resolved, [base]):
                continue

            existing = list_source_document_checksums(db, source_id=source_id)
            payload = build_document_payload(root=base, path=resolved, source_id=source_id)
            rel = str(payload.document["relative_path"])
            prior = existing.get(rel)
            if prior and prior[1] == payload.document["checksum"]:
                results.append({"source_id": source_id, "skipped": True, "relative_path": rel})
                continue

            sync_result = _sync_single_file_source(
                source=source,
                payload=payload,
                actor_email=_AUTO_SYNC_ACTOR,
                compute_embeddings=compute_embeddings,
            )
            results.append(
                {
                    "source_id": source_id,
                    "relative_path": rel,
                    "upserted": True,
                    "chunks": sync_result.chunks,
                }
            )
        return {"synced": bool(results), "sources": results}
    finally:
        try:
            db.close()
        except Exception:
            pass


def _sync_single_file_source(
    *,
    source: dict[str, Any],
    payload: Any,
    actor_email: str,
    compute_embeddings: bool,
) -> SyncResult:
    source_id = str(source["source_id"])
    tenant_id = str(source.get("tenant_id") or "default")
    project_id = str(source.get("project_id") or "")
    worker_uid = str(source.get("worker_uid") or "")
    result = SyncResult(source_id=source_id)

    ingest_task_ids, chunks = ingest_folder_payloads(
        source_id=source_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
        project_id=project_id,
        worker_uid=worker_uid,
        compute_embeddings=compute_embeddings,
        payloads=[payload],
    )
    result.task_ids.extend(ingest_task_ids)
    result.upserted = 1
    result.chunks = chunks

    sync_stats = {
        "scanned": 1,
        "upserted": 1,
        "skipped": 0,
        "removed": 0,
        "chunks": chunks,
        "auto": True,
        "trigger": "write_output_document",
    }
    ready_cmd = CreateKnowledgeSourceCommand(
        source_id=source_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
        project_id=project_id,
        worker_uid=worker_uid,
        source_kind="folder",
        source_uri=str(source.get("source_uri") or ""),
        display_name=str(source.get("display_name") or ""),
        status="ready",
        metadata={
            **dict(source.get("metadata") or {}),
            "last_sync_at": datetime.now(timezone.utc).isoformat(),
            "sync_stats": sync_stats,
        },
    )
    result.task_ids.append(_enqueue_knowledge_command(ready_cmd))
    return result


def run_auto_sync_poll(*, compute_embeddings: bool = True) -> list[SyncResult]:
    """Poll all folder sources; sync when vault mtime fingerprint changes."""
    if not auto_sync_enabled():
        return []

    db = _open_hub_db()
    if db is None:
        return []

    outcomes: list[SyncResult] = []
    try:
        from duckclaw.admin_knowledge_read import list_folder_knowledge_sources, list_source_document_checksums

        sources = list_folder_knowledge_sources(db)
        for source in sources:
            source_id = str(source["source_id"])
            try:
                existing = list_source_document_checksums(db, source_id=source_id)
                outcome = execute_folder_sync(
                    source=source,
                    existing=existing,
                    actor_email=_AUTO_SYNC_ACTOR,
                    compute_embeddings=compute_embeddings,
                    force=False,
                )
                if outcome.skipped_reason in ("unchanged_fingerprint", "no_changes"):
                    continue
                if outcome.upserted or outcome.removed:
                    _log.info(
                        "knowledge auto-sync source=%s upserted=%s removed=%s skipped=%s",
                        source_id,
                        outcome.upserted,
                        outcome.removed,
                        outcome.skipped,
                    )
                outcomes.append(outcome)
            except Exception as exc:
                _log.warning("knowledge auto-sync failed for %s: %s", source_id, exc)
    finally:
        try:
            db.close()
        except Exception:
            pass
    return outcomes
