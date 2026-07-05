"""RAG / knowledge admin routes (sources, uploads, search).

Gateway is enqueue-only for indexing mutations. DuckClaw-Knowledge-Indexer consumes Redis jobs.
Spec: docs/specs/features/platform/GATEWAY_PROCESS_BOUNDARIES.md
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)

from routers.admin_domains.admin_common import (
    actor_from_header,
    problem,
    require_admin_key,
)

router = APIRouter(tags=["admin-knowledge"])

_KNOWLEDGE_UPLOAD_MAX_FILES = 40
_KNOWLEDGE_UPLOAD_MAX_BYTES = 5 * 1024 * 1024


def _upload_display_name(explicit: str, uploaded_names: list[str]) -> str:
    cleaned = (explicit or "").strip()
    if cleaned:
        return cleaned[:160]
    if not uploaded_names:
        return "Carga de archivos"
    if len(uploaded_names) == 1:
        return uploaded_names[0][:160]
    primary = uploaded_names[0]
    suffix = f" (+{len(uploaded_names) - 1} más)"
    budget = max(1, 160 - len(suffix))
    return f"{primary[:budget]}{suffix}"


def _upload_filename_labels(files: list[UploadFile]) -> list[str]:
    labels: list[str] = []
    for upload in files:
        raw = (upload.filename or "").replace("\\", "/").strip()
        if not raw:
            continue
        name = Path(raw).name.strip()
        if name:
            labels.append(name)
    return labels


class KnowledgeSourceCreateBody(BaseModel):
    source_uri: str = Field(..., min_length=1, max_length=4096)
    display_name: str = Field(default="", max_length=160)
    source_kind: str = Field(default="folder", max_length=32)
    project_id: str = Field(default="", max_length=128)
    worker_uid: str = Field(default="", max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)
    ingest: bool = True
    compute_embeddings: bool = True


class KnowledgeSearchBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    project_id: str = Field(default="", max_length=128)
    worker_uid: str = Field(default="", max_length=128)
    source_id: str = Field(default="", max_length=128)
    limit: int = 8


class KnowledgeSyncBody(BaseModel):
    compute_embeddings: bool = True


class KnowledgeFolderPreviewBody(BaseModel):
    source_uri: str = Field(..., min_length=1, max_length=4096)


def _enqueue_knowledge_command(command: Any) -> str:
    from duckclaw.gateway_enqueue import enqueue_admin_command

    return enqueue_admin_command(command)


def _validate_knowledge_ingest_root(source_uri: str) -> Path:
    from duckclaw.forge.rag.knowledge_paths import validate_knowledge_ingest_root

    return validate_knowledge_ingest_root(source_uri)


@router.get("/knowledge/jobs/{job_id}", dependencies=[Depends(require_admin_key)])
async def get_knowledge_sync_job(job_id: str) -> dict[str, Any]:
    from duckclaw.knowledge_sync_queue import get_job_status

    row = get_job_status(job_id.strip())
    if not row:
        raise problem(404, f"Job de indexación no encontrado: {job_id}", job_id)
    return {"job_id": job_id.strip(), **row}


@router.get("/knowledge/config", dependencies=[Depends(require_admin_key)])
async def knowledge_config() -> dict[str, Any]:
    from duckclaw.forge.rag.knowledge_auto_sync import auto_sync_enabled, auto_sync_poll_seconds
    from duckclaw.forge.rag.knowledge_paths import knowledge_allowed_roots, knowledge_output_roots
    from duckclaw.knowledge_sync_queue import KNOWLEDGE_SYNC_QUEUE_KEY
    from duckclaw.process_role import embed_knowledge_sync_in_gateway, is_knowledge_indexer_process

    def _root_row(path: Path) -> dict[str, Any]:
        return {
            "path": str(path),
            "label": path.name or str(path),
            "exists": path.exists(),
        }

    return {
        "allowed_roots": [_root_row(p) for p in knowledge_allowed_roots()],
        "output_roots": [_root_row(p) for p in knowledge_output_roots()],
        "auto_sync": auto_sync_enabled(),
        "auto_sync_poll_sec": auto_sync_poll_seconds(),
        "indexer_queue": KNOWLEDGE_SYNC_QUEUE_KEY,
        "indexer_embedded_in_gateway": embed_knowledge_sync_in_gateway(),
        "gateway_enqueue_only": True,
        "process_role": "knowledge-indexer" if is_knowledge_indexer_process() else "gateway",
    }


@router.get("/knowledge/sources", dependencies=[Depends(require_admin_key)])
async def list_knowledge_sources(
    project_id: str = "",
    worker_uid: str = "",
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from core.heavy_work import run_heavy_work
    from duckclaw.admin_knowledge_read import list_knowledge_sources as _list_sources
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)

        def _list() -> list[dict[str, Any]]:
            return _list_sources(
                db,
                tenant_id=profile["tenant_id"],
                project_id=project_id,
                worker_uid=worker_uid,
            )

        sources = await run_heavy_work(_list)
    return {"sources": sources}


@router.post("/knowledge/sources/preview", dependencies=[Depends(require_admin_key)])
async def preview_knowledge_folder(body: KnowledgeFolderPreviewBody) -> dict[str, Any]:
    from core.heavy_work import run_heavy_work
    from duckclaw.forge.rag.knowledge_core import scan_knowledge_folder

    try:
        root = _validate_knowledge_ingest_root(body.source_uri)

        def _scan() -> dict[str, Any]:
            scan = scan_knowledge_folder(root)
            base = root if root.is_dir() else root.parent
            sample_paths = [
                str(p.resolve().relative_to(base.resolve())).replace("\\", "/")
                for p in scan.files[:8]
            ]
            return {
                "file_count": scan.file_count,
                "skipped_hidden": scan.skipped_hidden,
                "skipped_secret": scan.skipped_secret,
                "skipped_unsupported": scan.skipped_unsupported,
                "sample_paths": sample_paths,
            }

        stats = await run_heavy_work(_scan)
        return {"ok": True, "source_uri": str(root), **stats}
    except Exception as exc:
        raise problem(400, str(exc), "knowledge_preview") from exc


@router.post("/knowledge/sources", dependencies=[Depends(require_admin_key)])
async def create_knowledge_source(
    body: KnowledgeSourceCreateBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.knowledge_sync_queue import enqueue_knowledge_sync_job
    from duckclaw.write_commands import CreateKnowledgeSourceCommand

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)

    try:
        source_id = f"ksrc_{uuid.uuid4().hex[:16]}"
        command = CreateKnowledgeSourceCommand(
            source_id=source_id,
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            project_id=body.project_id.strip(),
            worker_uid=body.worker_uid.strip(),
            source_kind=body.source_kind.strip() or "folder",  # type: ignore[arg-type]
            source_uri=body.source_uri.strip(),
            display_name=body.display_name.strip(),
            status="indexing" if body.ingest else "pending",
            metadata=body.metadata,
        )
        task_ids = [_enqueue_knowledge_command(command)]
        documents = 0
        skipped_hidden = 0
        skipped_unsupported = 0
        sync_job_id = ""
        if body.ingest:
            root = _validate_knowledge_ingest_root(body.source_uri)
            from duckclaw.forge.rag.knowledge_core import scan_knowledge_folder

            scan = scan_knowledge_folder(root)
            if scan.file_count == 0:
                raise ValueError(
                    "No hay archivos indexables (.md, .txt, .pdf…) en esa carpeta. "
                    "Revisa la ruta o sube archivos manualmente."
                )
            documents = scan.file_count
            skipped_hidden = scan.skipped_hidden
            skipped_unsupported = scan.skipped_unsupported
            sync_job_id = enqueue_knowledge_sync_job(
                kind="folder_ingest",
                source_id=source_id,
                tenant_id=profile["tenant_id"],
                actor_email=profile["email"],
                compute_embeddings=body.compute_embeddings,
            )
    except Exception as exc:
        raise problem(400, str(exc), "knowledge_source") from exc

    return {
        "ok": True,
        "source_id": source_id,
        "status": "indexing" if body.ingest and documents > 0 else "pending",
        "task_ids": task_ids,
        "sync_job_id": sync_job_id,
        "documents": documents,
        "chunks": 0,
        "skipped_hidden": skipped_hidden,
        "skipped_unsupported": skipped_unsupported,
        "message": (
            "Indexación encolada en DuckClaw-Knowledge-Indexer."
            if sync_job_id
            else None
        ),
    }


@router.post("/knowledge/uploads", dependencies=[Depends(require_admin_key)])
async def upload_knowledge_files(
    project_id: str = Form(default=""),
    worker_uid: str = Form(default=""),
    display_name: str = Form(default=""),
    compute_embeddings: bool = Form(default=True),
    files: list[UploadFile] = File(...),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.knowledge_sync_queue import enqueue_browser_upload_job
    from duckclaw.knowledge_upload_staging import stage_browser_upload
    from duckclaw.write_commands import CreateKnowledgeSourceCommand

    if not files:
        raise problem(400, "Debes subir al menos un archivo", "knowledge_upload")
    if len(files) > _KNOWLEDGE_UPLOAD_MAX_FILES:
        raise problem(400, f"Máximo {_KNOWLEDGE_UPLOAD_MAX_FILES} archivos por carga", "knowledge_upload")

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)

    file_payloads: list[tuple[str, bytes]] = []
    for upload in files:
        data = await upload.read()
        if not data:
            continue
        if len(data) > _KNOWLEDGE_UPLOAD_MAX_BYTES:
            raise problem(400, f"{upload.filename or 'archivo'} supera 5MB", "knowledge_upload")
        file_payloads.append((upload.filename or f"upload-{len(file_payloads)}.txt", data))

    if not file_payloads:
        raise problem(400, "Debes subir al menos un archivo con contenido", "knowledge_upload")

    try:
        source_id = f"ksrc_{uuid.uuid4().hex[:16]}"
        upload_labels = [name for name, _data in file_payloads]
        resolved_display = _upload_display_name(display_name, upload_labels)
        source_cmd = CreateKnowledgeSourceCommand(
            source_id=source_id,
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            project_id=project_id.strip(),
            worker_uid=worker_uid.strip(),
            source_kind="file",
            source_uri=f"upload://{source_id}",
            display_name=resolved_display,
            status="indexing",
            metadata={"upload": True, "file_count": len(file_payloads), "file_names": upload_labels},
        )
        task_id = _enqueue_knowledge_command(source_cmd)
        job_id = enqueue_browser_upload_job(
            source_id=source_id,
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            staging_dir=str(stage_browser_upload(job_id=f"kupload_{source_id}", files=file_payloads)),
            project_id=project_id.strip(),
            worker_uid=worker_uid.strip(),
            display_name=resolved_display,
            file_names=upload_labels,
            compute_embeddings=compute_embeddings,
        )
    except Exception as exc:
        raise problem(400, "No se pudo encolar la carga RAG", str(exc)) from exc

    return {
        "ok": True,
        "accepted": True,
        "source_id": source_id,
        "status": "indexing",
        "task_ids": [task_id],
        "sync_job_id": job_id,
        "documents": len(file_payloads),
        "chunks": 0,
        "message": "Carga encolada en DuckClaw-Knowledge-Indexer.",
    }


@router.post("/knowledge/sources/{source_id}/sync", dependencies=[Depends(require_admin_key)])
async def sync_knowledge_source(
    source_id: str,
    body: KnowledgeSyncBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_knowledge_read import get_knowledge_source
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.knowledge_sync_queue import enqueue_knowledge_sync_job
    from duckclaw.write_commands import CreateKnowledgeSourceCommand

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)
        source = get_knowledge_source(db, tenant_id=profile["tenant_id"], source_id=source_id)
        if not source:
            raise problem(404, f"Fuente RAG no encontrada: {source_id}", source_id)
        if str(source.get("source_kind") or "") != "folder":
            raise problem(400, "Solo fuentes tipo carpeta admiten sync incremental", source_id)
        source_uri = str(source.get("source_uri") or "").strip()
        if not source_uri or source_uri.startswith("upload://"):
            raise problem(400, "Esta fuente no tiene ruta de servidor para sincronizar", source_id)

    try:
        indexing_cmd = CreateKnowledgeSourceCommand(
            source_id=source_id,
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            project_id=str(source.get("project_id") or ""),
            worker_uid=str(source.get("worker_uid") or ""),
            source_kind="folder",
            source_uri=source_uri,
            display_name=str(source.get("display_name") or ""),
            status="indexing",
            metadata=dict(source.get("metadata") or {}),
        )
        task_id = _enqueue_knowledge_command(indexing_cmd)
        sync_job_id = enqueue_knowledge_sync_job(
            kind="folder_sync",
            source_id=source_id,
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            force=True,
            compute_embeddings=body.compute_embeddings,
        )
    except Exception as exc:
        raise problem(400, str(exc), "knowledge_sync") from exc

    return {
        "ok": True,
        "accepted": True,
        "source_id": source_id,
        "status": "indexing",
        "task_ids": [task_id],
        "sync_job_id": sync_job_id,
        "message": "Sincronización encolada en DuckClaw-Knowledge-Indexer.",
    }


@router.delete("/knowledge/sources/{source_id}", dependencies=[Depends(require_admin_key)])
async def deactivate_knowledge_source(
    source_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.write_commands import DeactivateKnowledgeSourceCommand

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)
    try:
        command = DeactivateKnowledgeSourceCommand(
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            source_id=source_id,
        )
        task_id = _enqueue_knowledge_command(command)
    except ValueError as exc:
        raise problem(404, str(exc), source_id) from exc
    return {"ok": True, "source_id": source_id, "task_id": task_id}


@router.post("/knowledge/search", dependencies=[Depends(require_admin_key)])
async def search_knowledge(
    body: KnowledgeSearchBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from core.heavy_work import run_heavy_work
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.forge.rag.knowledge_core import search_knowledge as _search

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)

        def _search_rows() -> list[dict[str, Any]]:
            return _search(
                db,
                query=body.query,
                tenant_id=profile["tenant_id"],
                project_id=body.project_id.strip(),
                worker_uid=body.worker_uid.strip(),
                source_id=body.source_id.strip(),
                limit=body.limit,
            )

        rows = await run_heavy_work(_search_rows)
    return {"results": rows, "count": len(rows)}
