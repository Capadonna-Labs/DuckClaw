"""Execute knowledge folder sync (admin, auto-poll, post-write)."""

from __future__ import annotations

import gc
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from duckclaw.forge.rag.knowledge_core import build_document_payload
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
_sync_lock = threading.Lock()


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
    raw = (os.environ.get("DUCKCLAW_KNOWLEDGE_AUTO_SYNC_POLL_SEC") or "60").strip()
    try:
        return max(15, int(raw))
    except ValueError:
        return 60


def sync_max_files_per_run() -> int | None:
    raw = (os.environ.get("DUCKCLAW_KNOWLEDGE_SYNC_MAX_FILES") or "").strip()
    if not raw:
        return None
    try:
        return max(1, int(raw))
    except ValueError:
        return None


def knowledge_sync_in_progress() -> bool:
    return _sync_lock.locked()


def _enqueue_knowledge_command(command: Any) -> str:
    from duckclaw.db_write_fire_and_forget import enqueue_write_command
    from duckclaw.gateway_db import get_gateway_db_path

    return enqueue_write_command(
        command,
        db_path=get_gateway_db_path(),
        user_id="default",
    )


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
    from duckclaw.forge.rag.knowledge_core import embed_chunk_payloads

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


def ingest_folder_paths(
    *,
    root: Path,
    source_id: str,
    tenant_id: str,
    actor_email: str,
    project_id: str,
    worker_uid: str,
    compute_embeddings: bool,
    paths: list[Path],
) -> tuple[list[str], int]:
    """Ingest one file at a time to limit peak RAM (PDF/markitdown + embeddings)."""
    task_ids: list[str] = []
    chunks_total = 0
    base = root if root.is_dir() else root.parent
    for file_path in paths:
        payload = build_document_payload(root=base, path=file_path, source_id=source_id)
        file_task_ids, file_chunks = ingest_folder_payloads(
            source_id=source_id,
            tenant_id=tenant_id,
            actor_email=actor_email,
            project_id=project_id,
            worker_uid=worker_uid,
            compute_embeddings=compute_embeddings,
            payloads=[payload],
        )
        task_ids.extend(file_task_ids)
        chunks_total += file_chunks
        del payload
        gc.collect()
    return task_ids, chunks_total


def execute_folder_sync(
    *,
    source: dict[str, Any],
    existing: dict[str, tuple[str, str, int]],
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

    if not _sync_lock.acquire(blocking=False):
        result.skipped_reason = "sync_in_progress"
        return result

    try:
        return _execute_folder_sync_locked(
            source=source,
            existing=existing,
            actor_email=actor_email,
            compute_embeddings=compute_embeddings,
            force=force,
        )
    finally:
        _sync_lock.release()


def _execute_folder_sync_locked(
    *,
    source: dict[str, Any],
    existing: dict[str, tuple[str, str, int]],
    actor_email: str,
    compute_embeddings: bool,
    force: bool,
) -> SyncResult:
    from duckclaw.knowledge_indexer_guard import assert_indexer_process_for_mutation

    assert_indexer_process_for_mutation(operation="folder_sync")
    source_id = str(source["source_id"])
    source_uri = str(source.get("source_uri") or "").strip()
    result = SyncResult(source_id=source_id)

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

    plan = plan_folder_sync(root=root, source_id=source_id, existing=existing, force=force)
    if not force and not plan.to_upsert_paths and not plan.to_deactivate:
        _last_fingerprint[source_id] = fingerprint
        result.scanned = plan.scanned
        result.skipped = plan.skipped
        result.skipped_reason = "no_changes"
        return result

    upsert_paths = list(plan.to_upsert_paths)
    max_files = sync_max_files_per_run()
    if max_files is not None and len(upsert_paths) > max_files:
        upsert_paths = upsert_paths[:max_files]
        _log.info(
            "knowledge sync source=%s capped upsert batch to %s files (max=%s)",
            source_id,
            len(upsert_paths),
            max_files,
        )

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

    ingest_task_ids, chunks = ingest_folder_paths(
        root=root,
        source_id=source_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
        project_id=project_id,
        worker_uid=worker_uid,
        compute_embeddings=compute_embeddings,
        paths=upsert_paths,
    )
    result.task_ids.extend(ingest_task_ids)
    result.scanned = plan.scanned
    result.upserted = len(upsert_paths)
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
    if max_files is None or len(plan.to_upsert_paths) <= max_files:
        _last_fingerprint[source_id] = fingerprint
    return result


def execute_folder_ingest_for_source(
    *,
    source: dict[str, Any],
    actor_email: str,
    compute_embeddings: bool = True,
) -> SyncResult:
    """Full folder ingest for a registered source (create/import flow)."""
    from duckclaw.knowledge_indexer_guard import assert_indexer_process_for_mutation

    assert_indexer_process_for_mutation(operation="folder_ingest")
    source_id = str(source["source_id"])
    source_uri = str(source.get("source_uri") or "").strip()
    result = SyncResult(source_id=source_id)

    if not source_uri or source_uri.startswith("upload://"):
        result.skipped_reason = "not_a_folder_uri"
        return result

    if not _sync_lock.acquire(blocking=False):
        result.skipped_reason = "sync_in_progress"
        return result

    try:
        root = validate_knowledge_ingest_root(source_uri)
    except (ValueError, FileNotFoundError) as exc:
        _sync_lock.release()
        result.skipped_reason = str(exc)
        return result

    try:
        from duckclaw.forge.rag.knowledge_core import iter_allowed_files

        tenant_id = str(source.get("tenant_id") or "default")
        project_id = str(source.get("project_id") or "")
        worker_uid = str(source.get("worker_uid") or "")
        paths = iter_allowed_files(root)
        if not paths:
            result.skipped_reason = "no_indexable_files"
            return result

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

        ingest_task_ids, chunks = ingest_folder_paths(
            root=root,
            source_id=source_id,
            tenant_id=tenant_id,
            actor_email=actor_email,
            project_id=project_id,
            worker_uid=worker_uid,
            compute_embeddings=compute_embeddings,
            paths=paths,
        )
        result.task_ids.extend(ingest_task_ids)
        result.scanned = len(paths)
        result.upserted = len(paths)
        result.chunks = chunks

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
                "sync_stats": {
                    "scanned": result.scanned,
                    "upserted": result.upserted,
                    "skipped": 0,
                    "removed": 0,
                    "chunks": chunks,
                    "trigger": "folder_ingest",
                },
            },
        )
        result.task_ids.append(_enqueue_knowledge_command(ready_cmd))
        _last_fingerprint[source_id] = folder_mtime_fingerprint(root)
        return result
    finally:
        _sync_lock.release()


def execute_browser_upload_for_source(
    *,
    source: dict[str, Any],
    actor_email: str,
    staging_dir: str,
    compute_embeddings: bool = True,
) -> SyncResult:
    from duckclaw.forge.rag.knowledge_core import build_uploaded_document_payload
    from duckclaw.knowledge_indexer_guard import assert_indexer_process_for_mutation
    from duckclaw.knowledge_upload_staging import read_staged_upload_manifest

    assert_indexer_process_for_mutation(operation="browser_upload")
    source_id = str(source["source_id"])
    result = SyncResult(source_id=source_id)
    tenant_id = str(source.get("tenant_id") or "default")
    project_id = str(source.get("project_id") or "")
    worker_uid = str(source.get("worker_uid") or "")

    staged_paths = read_staged_upload_manifest(staging_dir)
    if not staged_paths:
        result.skipped_reason = "empty_staging"
        return result

    if not _sync_lock.acquire(blocking=False):
        result.skipped_reason = "sync_in_progress"
        return result

    try:
        indexing_cmd = CreateKnowledgeSourceCommand(
            source_id=source_id,
            tenant_id=tenant_id,
            actor_email=actor_email,
            project_id=project_id,
            worker_uid=worker_uid,
            source_kind="file",
            source_uri=f"upload://{source_id}",
            display_name=str(source.get("display_name") or ""),
            status="indexing",
            metadata=dict(source.get("metadata") or {}),
        )
        result.task_ids.append(_enqueue_knowledge_command(indexing_cmd))

        chunks_total = 0
        for staged_path in staged_paths:
            payload = build_uploaded_document_payload(
                filename=staged_path.name,
                data=staged_path.read_bytes(),
                source_id=source_id,
            )
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
            chunks_total += chunks
            del payload
            gc.collect()

        result.scanned = len(staged_paths)
        result.upserted = len(staged_paths)
        result.chunks = chunks_total

        ready_cmd = CreateKnowledgeSourceCommand(
            source_id=source_id,
            tenant_id=tenant_id,
            actor_email=actor_email,
            project_id=project_id,
            worker_uid=worker_uid,
            source_kind="file",
            source_uri=f"upload://{source_id}",
            display_name=str(source.get("display_name") or ""),
            status="ready",
            metadata={
                **dict(source.get("metadata") or {}),
                "upload": True,
                "documents": len(staged_paths),
                "chunks": chunks_total,
                "last_sync_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        result.task_ids.append(_enqueue_knowledge_command(ready_cmd))
        return result
    finally:
        _sync_lock.release()


def execute_single_file_sync_for_source(
    *,
    source: dict[str, Any],
    actor_email: str,
    file_path: Path,
    compute_embeddings: bool = True,
) -> SyncResult:
    from duckclaw.knowledge_indexer_guard import assert_indexer_process_for_mutation

    assert_indexer_process_for_mutation(operation="single_file_sync")
    source_id = str(source["source_id"])
    source_uri = str(source.get("source_uri") or "").strip()
    result = SyncResult(source_id=source_id)

    try:
        root = validate_knowledge_ingest_root(source_uri)
    except (ValueError, FileNotFoundError) as exc:
        result.skipped_reason = str(exc)
        return result

    base = root if root.is_dir() else root.parent
    resolved = file_path.expanduser().resolve()
    if not path_under_any_root(resolved, [base]):
        result.skipped_reason = "file_outside_source_root"
        return result

    payload = build_document_payload(root=base, path=resolved, source_id=source_id)
    return _sync_single_file_source(
        source=source,
        payload=payload,
        actor_email=actor_email,
        compute_embeddings=compute_embeddings,
    )


def _is_duckdb_lock_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "lock" in msg or "conflicting" in msg


def _vault_write_session_active() -> bool:
    try:
        from duckclaw.forge.skills.report_engine_hub_context import get_report_engine_hub_db

        reuse = get_report_engine_hub_db()
        if reuse is None:
            return False
        return not bool(getattr(reuse, "_read_only", True))
    except Exception:
        return False


def _open_hub_db() -> tuple[Any | None, bool]:
    """Return (connection, should_close). Reuses active hub without closing it."""
    from duckclaw.gateway_db import get_gateway_db_path

    path = (get_gateway_db_path() or "").strip()
    if not path:
        return None, False
    try:
        from duckclaw.forge.skills.report_engine_hub_context import get_report_engine_hub_db
        from duckclaw.state_delta_vault import _same_vault_db_path

        reuse = get_report_engine_hub_db()
        if reuse is not None and _same_vault_db_path(str(getattr(reuse, "_path", "") or ""), path):
            return reuse, False
    except Exception:
        pass
    try:
        from duckclaw import DuckClaw

        return DuckClaw(path, read_only=True), True
    except Exception as exc:
        if _is_duckdb_lock_error(exc):
            _log.debug("knowledge auto-sync: hub db ocupado, omitiendo ciclo: %s", exc)
            return None, False
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
    """Queue re-index of one written file — Gateway must not index inline."""
    if not auto_sync_enabled():
        return {"synced": False, "reason": "auto_sync_disabled"}

    if _vault_write_session_active():
        return {"synced": False, "reason": "vault_write_session_active"}

    db, close_db = _open_hub_db()
    if db is None:
        return {"synced": False, "reason": "no_hub_db"}

    job_ids: list[str] = []
    results: list[dict[str, Any]] = []
    try:
        sources = _folder_sources_containing_file(
            db,
            file_path=file_path,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        if not sources:
            return {"synced": False, "reason": "no_matching_source", "sources": []}

        resolved = file_path.expanduser().resolve()
        from duckclaw.knowledge_sync_queue import enqueue_single_file_sync_job

        for source in sources:
            source_id = str(source["source_id"])
            job_id = enqueue_single_file_sync_job(
                source_id=source_id,
                tenant_id=tenant_id,
                actor_email=_AUTO_SYNC_ACTOR,
                file_path=str(resolved),
                compute_embeddings=compute_embeddings,
            )
            job_ids.append(job_id)
            results.append({"source_id": source_id, "queued": True, "job_id": job_id})
        return {"synced": True, "queued": True, "job_ids": job_ids, "sources": results}
    finally:
        if close_db:
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
    from duckclaw.knowledge_indexer_guard import assert_indexer_process_for_mutation

    assert_indexer_process_for_mutation(operation="auto_sync_poll")
    if not auto_sync_enabled():
        return []

    if knowledge_sync_in_progress():
        _log.debug("knowledge auto-sync: sync manual/otro ciclo en curso, omitiendo")
        return []

    if _vault_write_session_active():
        _log.debug("knowledge auto-sync: vault RW en sesión activa, omitiendo ciclo")
        return []

    db, close_db = _open_hub_db()
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
                if _is_duckdb_lock_error(exc):
                    _log.debug(
                        "knowledge auto-sync deferred for %s (vault lock): %s",
                        source_id,
                        exc,
                    )
                    continue
                _log.warning("knowledge auto-sync failed for %s: %s", source_id, exc)
    finally:
        if close_db:
            try:
                db.close()
            except Exception:
                pass
    return outcomes
