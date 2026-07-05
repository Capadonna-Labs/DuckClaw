"""Redis queue for all knowledge indexing — consumed only by DuckClaw-Knowledge-Indexer."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

_log = logging.getLogger(__name__)

KNOWLEDGE_SYNC_QUEUE_KEY = "duckclaw:knowledge_sync_jobs"
KNOWLEDGE_SYNC_STATUS_PREFIX = "duckclaw:knowledge_sync_status:"
KNOWLEDGE_SYNC_STATUS_TTL_SEC = 86400

KnowledgeJobKind = Literal["folder_sync", "folder_ingest", "browser_upload", "single_file_sync"]


@dataclass(frozen=True)
class KnowledgeSyncJob:
    job_id: str
    kind: KnowledgeJobKind
    source_id: str
    tenant_id: str
    actor_email: str
    force: bool = False
    compute_embeddings: bool = True
    enqueued_at: float = 0.0
    project_id: str = ""
    worker_uid: str = ""
    display_name: str = ""
    staging_dir: str = ""
    file_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "job_id": self.job_id,
                "kind": self.kind,
                "source_id": self.source_id,
                "tenant_id": self.tenant_id,
                "actor_email": self.actor_email,
                "force": self.force,
                "compute_embeddings": self.compute_embeddings,
                "enqueued_at": self.enqueued_at,
                "project_id": self.project_id,
                "worker_uid": self.worker_uid,
                "display_name": self.display_name,
                "staging_dir": self.staging_dir,
                "file_path": self.file_path,
                "metadata": self.metadata,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str) -> KnowledgeSyncJob:
        data = json.loads(raw)
        meta = data.get("metadata")
        return cls(
            job_id=str(data["job_id"]),
            kind=data["kind"],  # type: ignore[arg-type]
            source_id=str(data["source_id"]),
            tenant_id=str(data["tenant_id"]),
            actor_email=str(data["actor_email"]),
            force=bool(data.get("force")),
            compute_embeddings=bool(data.get("compute_embeddings", True)),
            enqueued_at=float(data.get("enqueued_at") or time.time()),
            project_id=str(data.get("project_id") or ""),
            worker_uid=str(data.get("worker_uid") or ""),
            display_name=str(data.get("display_name") or ""),
            staging_dir=str(data.get("staging_dir") or ""),
            file_path=str(data.get("file_path") or ""),
            metadata=dict(meta) if isinstance(meta, dict) else {},
        )


def _redis_client():
    import redis

    from duckclaw.runtime_env import resolve_redis_url

    return redis.from_url(resolve_redis_url(), decode_responses=True)


def _status_key(job_id: str) -> str:
    return f"{KNOWLEDGE_SYNC_STATUS_PREFIX}{job_id}"


def set_job_status(job_id: str, *, status: str, detail: str = "") -> None:
    client = _redis_client()
    payload = json.dumps({"status": status, "detail": detail, "updated_at": time.time()})
    client.set(_status_key(job_id), payload, ex=KNOWLEDGE_SYNC_STATUS_TTL_SEC)


def get_job_status(job_id: str) -> dict[str, Any] | None:
    client = _redis_client()
    raw = client.get(_status_key(job_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _new_job_id() -> str:
    return f"ksync_{uuid.uuid4().hex[:16]}"


def _push_job(job: KnowledgeSyncJob) -> str:
    client = _redis_client()
    client.lpush(KNOWLEDGE_SYNC_QUEUE_KEY, job.to_json())
    set_job_status(job.job_id, status="queued")
    _log.info("knowledge job queued kind=%s source=%s job_id=%s", job.kind, job.source_id, job.job_id)
    return job.job_id


def enqueue_knowledge_sync_job(
    *,
    kind: KnowledgeJobKind,
    source_id: str,
    tenant_id: str,
    actor_email: str,
    force: bool = False,
    compute_embeddings: bool = True,
    project_id: str = "",
    worker_uid: str = "",
    display_name: str = "",
    staging_dir: str = "",
    file_path: str = "",
    metadata: dict[str, Any] | None = None,
) -> str:
    job = KnowledgeSyncJob(
        job_id=_new_job_id(),
        kind=kind,
        source_id=source_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
        force=force,
        compute_embeddings=compute_embeddings,
        enqueued_at=time.time(),
        project_id=project_id,
        worker_uid=worker_uid,
        display_name=display_name,
        staging_dir=staging_dir,
        file_path=file_path,
        metadata=dict(metadata or {}),
    )
    return _push_job(job)


def enqueue_browser_upload_job(
    *,
    source_id: str,
    tenant_id: str,
    actor_email: str,
    staging_dir: str,
    project_id: str,
    worker_uid: str,
    display_name: str,
    file_names: list[str],
    compute_embeddings: bool = True,
) -> str:
    return enqueue_knowledge_sync_job(
        kind="browser_upload",
        source_id=source_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
        compute_embeddings=compute_embeddings,
        project_id=project_id,
        worker_uid=worker_uid,
        display_name=display_name,
        staging_dir=staging_dir,
        metadata={"file_names": file_names, "upload": True},
    )


def enqueue_single_file_sync_job(
    *,
    source_id: str,
    tenant_id: str,
    actor_email: str,
    file_path: str,
    compute_embeddings: bool = True,
) -> str:
    return enqueue_knowledge_sync_job(
        kind="single_file_sync",
        source_id=source_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
        compute_embeddings=compute_embeddings,
        file_path=file_path,
    )


def knowledge_sync_queue_depth() -> int | None:
    try:
        client = _redis_client()
        return int(client.llen(KNOWLEDGE_SYNC_QUEUE_KEY))
    except Exception:
        return None


def dequeue_knowledge_sync_job(*, block_timeout_sec: float = 2.0) -> KnowledgeSyncJob | None:
    client = _redis_client()
    if block_timeout_sec > 0:
        item = client.brpop(KNOWLEDGE_SYNC_QUEUE_KEY, timeout=max(1, int(block_timeout_sec)))
        if not item:
            return None
        _key, raw = item
    else:
        raw = client.rpop(KNOWLEDGE_SYNC_QUEUE_KEY)
        if not raw:
            return None
    try:
        return KnowledgeSyncJob.from_json(str(raw))
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        _log.warning("knowledge job parse failed: %s", exc)
        return None


def _open_hub_db_readonly():
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path

    db_path = (get_gateway_db_path() or "").strip()
    if not db_path:
        return None, None
    return DuckClaw(db_path, read_only=True), db_path


def process_knowledge_sync_job(job: KnowledgeSyncJob) -> dict[str, Any]:
    """Execute one queued job — only valid inside DuckClaw-Knowledge-Indexer."""
    from duckclaw.admin_knowledge_read import get_knowledge_source, list_source_document_checksums
    from duckclaw.forge.rag.knowledge_auto_sync import (
        execute_browser_upload_for_source,
        execute_folder_ingest_for_source,
        execute_folder_sync,
        execute_single_file_sync_for_source,
    )

    set_job_status(job.job_id, status="running")
    db, _db_path = _open_hub_db_readonly()
    if db is None:
        set_job_status(job.job_id, status="failed", detail="no_hub_db")
        return {"ok": False, "reason": "no_hub_db"}

    try:
        if job.kind == "browser_upload":
            source = get_knowledge_source(db, tenant_id=job.tenant_id, source_id=job.source_id)
            if not source:
                set_job_status(job.job_id, status="failed", detail="source_not_found")
                return {"ok": False, "reason": "source_not_found"}
            outcome = execute_browser_upload_for_source(
                source=source,
                actor_email=job.actor_email,
                staging_dir=job.staging_dir,
                compute_embeddings=job.compute_embeddings,
            )
        elif job.kind == "single_file_sync":
            source = get_knowledge_source(db, tenant_id=job.tenant_id, source_id=job.source_id)
            if not source:
                set_job_status(job.job_id, status="failed", detail="source_not_found")
                return {"ok": False, "reason": "source_not_found"}
            outcome = execute_single_file_sync_for_source(
                source=source,
                actor_email=job.actor_email,
                file_path=Path(job.file_path),
                compute_embeddings=job.compute_embeddings,
            )
        elif job.kind == "folder_ingest":
            source = get_knowledge_source(db, tenant_id=job.tenant_id, source_id=job.source_id)
            if not source:
                set_job_status(job.job_id, status="failed", detail="source_not_found")
                return {"ok": False, "reason": "source_not_found"}
            outcome = execute_folder_ingest_for_source(
                source=source,
                actor_email=job.actor_email,
                compute_embeddings=job.compute_embeddings,
            )
        else:
            source = get_knowledge_source(db, tenant_id=job.tenant_id, source_id=job.source_id)
            if not source:
                set_job_status(job.job_id, status="failed", detail="source_not_found")
                return {"ok": False, "reason": "source_not_found"}
            existing = list_source_document_checksums(db, source_id=job.source_id)
            outcome = execute_folder_sync(
                source=source,
                existing=existing,
                actor_email=job.actor_email,
                compute_embeddings=job.compute_embeddings,
                force=job.force,
            )
    finally:
        db.close()

    if outcome.skipped_reason == "sync_in_progress":
        set_job_status(job.job_id, status="deferred", detail=outcome.skipped_reason)
        return {"ok": False, "deferred": True, "reason": outcome.skipped_reason}

    if job.kind == "browser_upload" and job.staging_dir:
        from duckclaw.knowledge_upload_staging import cleanup_staging_dir

        cleanup_staging_dir(job.staging_dir)

    detail = json.dumps(
        {
            "scanned": outcome.scanned,
            "upserted": outcome.upserted,
            "skipped": outcome.skipped,
            "removed": outcome.removed,
            "chunks": outcome.chunks,
        }
    )
    set_job_status(job.job_id, status="completed", detail=detail)
    return {
        "ok": True,
        "job_id": job.job_id,
        "kind": job.kind,
        "scanned": outcome.scanned,
        "upserted": outcome.upserted,
        "skipped": outcome.skipped,
        "removed": outcome.removed,
        "chunks": outcome.chunks,
    }


def run_knowledge_indexer_cycle(*, block_timeout_sec: float = 2.0) -> dict[str, Any]:
    job = dequeue_knowledge_sync_job(block_timeout_sec=block_timeout_sec)
    if job is None:
        return {"processed": False}
    try:
        result = process_knowledge_sync_job(job)
        return {"processed": True, **result}
    except Exception as exc:
        _log.exception("knowledge job failed job_id=%s kind=%s", job.job_id, job.kind)
        set_job_status(job.job_id, status="failed", detail=str(exc)[:500])
        if job.kind == "browser_upload" and job.staging_dir:
            from duckclaw.knowledge_upload_staging import cleanup_staging_dir

            cleanup_staging_dir(job.staging_dir)
        return {"processed": True, "ok": False, "error": str(exc)}
