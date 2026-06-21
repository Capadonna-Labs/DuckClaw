"""RAG / knowledge admin routes (sources, uploads, search)."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile
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
    from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync
    from duckclaw.gateway_db import get_gateway_db_path

    task_id = enqueue_typed_command(command, db_path=get_gateway_db_path(), user_id="default")
    status = poll_task_status_sync(task_id, timeout_sec=0.5)
    if status and status.status == "failed":
        detail = status.detail or "knowledge write failed"
        if "No hay query SQL" in detail:
            raise ValueError(
                "DB-Writer desactualizado: reinicia DuckClaw-DB-Writer y DuckClaw-Gateway para aplicar comandos RAG tipados."
            )
        raise ValueError(detail)
    return task_id


def _validate_knowledge_ingest_root(source_uri: str) -> Path:
    from duckclaw.forge.rag.knowledge_paths import validate_knowledge_ingest_root

    return validate_knowledge_ingest_root(source_uri)


def _ingest_folder_payloads(
    *,
    source_id: str,
    tenant_id: str,
    actor_email: str,
    project_id: str,
    worker_uid: str,
    compute_embeddings: bool,
    payloads: list[Any],
) -> tuple[list[str], int]:
    from duckclaw.forge.rag.knowledge_auto_sync import ingest_folder_payloads

    return ingest_folder_payloads(
        source_id=source_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
        project_id=project_id,
        worker_uid=worker_uid,
        compute_embeddings=compute_embeddings,
        payloads=payloads,
    )


def _complete_folder_ingest(
    *,
    source_id: str,
    tenant_id: str,
    actor_email: str,
    project_id: str,
    worker_uid: str,
    source_kind: str,
    source_uri: str,
    display_name: str,
    metadata: dict[str, Any],
    compute_embeddings: bool,
    payloads: list[Any],
    skipped_hidden: int,
    skipped_unsupported: int,
) -> None:
    """Background ingest: evita HTTP 500 por timeout en vaults grandes."""
    from duckclaw.write_commands import CreateKnowledgeSourceCommand

    documents = len(payloads)
    try:
        _ingest_folder_payloads(
            source_id=source_id,
            tenant_id=tenant_id,
            actor_email=actor_email,
            project_id=project_id,
            worker_uid=worker_uid,
            compute_embeddings=compute_embeddings,
            payloads=payloads,
        )
        ingest_meta = {
            "documents": documents,
            "skipped_hidden": skipped_hidden,
            "skipped_unsupported": skipped_unsupported,
        }
        ready_cmd = CreateKnowledgeSourceCommand(
            source_id=source_id,
            tenant_id=tenant_id,
            actor_email=actor_email,
            project_id=project_id,
            worker_uid=worker_uid,
            source_kind=source_kind,  # type: ignore[arg-type]
            source_uri=source_uri,
            display_name=display_name,
            status="ready",
            metadata={**metadata, **ingest_meta},
        )
        _enqueue_knowledge_command(ready_cmd)
    except Exception as exc:
        _log.exception("folder ingest failed source_id=%s", source_id)
        fail_cmd = CreateKnowledgeSourceCommand(
            source_id=source_id,
            tenant_id=tenant_id,
            actor_email=actor_email,
            project_id=project_id,
            worker_uid=worker_uid,
            source_kind=source_kind,  # type: ignore[arg-type]
            source_uri=source_uri,
            display_name=display_name,
            status="failed",
            metadata={**metadata, "error": str(exc)[:500], "documents": documents},
        )
        try:
            _enqueue_knowledge_command(fail_cmd)
        except Exception:
            _log.exception("could not mark knowledge source failed source_id=%s", source_id)


@router.get("/knowledge/config", dependencies=[Depends(require_admin_key)])
async def knowledge_config() -> dict[str, Any]:
    from duckclaw.forge.rag.knowledge_auto_sync import auto_sync_enabled, auto_sync_poll_seconds
    from duckclaw.forge.rag.knowledge_paths import knowledge_allowed_roots, knowledge_output_roots

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
    }


@router.get("/knowledge/sources", dependencies=[Depends(require_admin_key)])
async def list_knowledge_sources(
    project_id: str = "",
    worker_uid: str = "",
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_knowledge_read import list_knowledge_sources as _list_sources
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)
        sources = _list_sources(
            db,
            tenant_id=profile["tenant_id"],
            project_id=project_id,
            worker_uid=worker_uid,
        )
    return {"sources": sources}


@router.post("/knowledge/sources/preview", dependencies=[Depends(require_admin_key)])
async def preview_knowledge_folder(body: KnowledgeFolderPreviewBody) -> dict[str, Any]:
    from duckclaw.forge.rag.knowledge_core import scan_knowledge_folder

    try:
        root = _validate_knowledge_ingest_root(body.source_uri)
        scan = scan_knowledge_folder(root)
        base = root if root.is_dir() else root.parent
        sample_paths = [
            str(p.resolve().relative_to(base.resolve())).replace("\\", "/")
            for p in scan.files[:8]
        ]
        return {
            "ok": True,
            "source_uri": str(root),
            "file_count": scan.file_count,
            "skipped_hidden": scan.skipped_hidden,
            "skipped_secret": scan.skipped_secret,
            "skipped_unsupported": scan.skipped_unsupported,
            "sample_paths": sample_paths,
        }
    except Exception as exc:
        raise problem(400, str(exc), "knowledge_preview") from exc


@router.post("/knowledge/sources", dependencies=[Depends(require_admin_key)])
async def create_knowledge_source(
    body: KnowledgeSourceCreateBody,
    background_tasks: BackgroundTasks,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user
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
        chunks = 0
        skipped_hidden = 0
        skipped_unsupported = 0
        if body.ingest:
            root = _validate_knowledge_ingest_root(body.source_uri)
            from duckclaw.forge.rag.knowledge_core import build_document_payload, scan_knowledge_folder

            scan = scan_knowledge_folder(root)
            if scan.file_count == 0:
                raise ValueError(
                    "No hay archivos indexables (.md, .txt, .pdf…) en esa carpeta. "
                    "Revisa la ruta o sube archivos manualmente."
                )
            payloads = [
                build_document_payload(
                    root=root if root.is_dir() else root.parent,
                    path=file_path,
                    source_id=source_id,
                )
                for file_path in scan.files
            ]
            documents = len(payloads)
            skipped_hidden = scan.skipped_hidden
            skipped_unsupported = scan.skipped_unsupported
            background_tasks.add_task(
                _complete_folder_ingest,
                source_id=source_id,
                tenant_id=profile["tenant_id"],
                actor_email=profile["email"],
                project_id=body.project_id.strip(),
                worker_uid=body.worker_uid.strip(),
                source_kind=body.source_kind.strip() or "folder",
                source_uri=body.source_uri.strip(),
                display_name=body.display_name.strip(),
                metadata=body.metadata,
                compute_embeddings=body.compute_embeddings,
                payloads=payloads,
                skipped_hidden=skipped_hidden,
                skipped_unsupported=skipped_unsupported,
            )
    except Exception as exc:
        raise problem(400, str(exc), "knowledge_source") from exc

    return {
        "ok": True,
        "source_id": source_id,
        "status": "indexing" if body.ingest and documents > 0 else "pending",
        "task_ids": task_ids,
        "documents": documents,
        "chunks": chunks,
        "skipped_hidden": skipped_hidden,
        "skipped_unsupported": skipped_unsupported,
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
    from duckclaw.forge.rag.knowledge_core import build_uploaded_document_payload, embed_chunk_payloads
    from duckclaw.write_commands import (
        CreateKnowledgeSourceCommand,
        UpsertKnowledgeChunksCommand,
        UpsertKnowledgeDocumentCommand,
    )

    if not files:
        raise problem(400, "Debes subir al menos un archivo", "knowledge_upload")
    if len(files) > _KNOWLEDGE_UPLOAD_MAX_FILES:
        raise problem(400, f"Máximo {_KNOWLEDGE_UPLOAD_MAX_FILES} archivos por carga", "knowledge_upload")

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)

    try:
        source_id = f"ksrc_{uuid.uuid4().hex[:16]}"
        task_ids: list[str] = []
        upload_labels = _upload_filename_labels(files)
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
            metadata={"upload": True, "file_count": len(files), "file_names": upload_labels},
        )
        task_ids.append(_enqueue_knowledge_command(source_cmd))

        embedding_fn = None
        if compute_embeddings:
            from duckclaw.forge.rag.embeddings import embed_text

            embedding_fn = embed_text
        documents = 0
        chunks = 0
        for upload in files:
            data = await upload.read()
            if not data:
                continue
            if len(data) > _KNOWLEDGE_UPLOAD_MAX_BYTES:
                raise ValueError(f"{upload.filename or 'archivo'} supera 5MB")
            payload = build_uploaded_document_payload(
                filename=upload.filename or f"upload-{documents}.txt",
                data=data,
                source_id=source_id,
            )
            doc_cmd = UpsertKnowledgeDocumentCommand(
                tenant_id=profile["tenant_id"],
                actor_email=profile["email"],
                **payload.document,
            )
            task_ids.append(_enqueue_knowledge_command(doc_cmd))
            chunk_payloads = (
                embed_chunk_payloads(payload.chunks, embedding_fn)
                if embedding_fn is not None
                else payload.chunks
            )
            chunk_cmd = UpsertKnowledgeChunksCommand(
                tenant_id=profile["tenant_id"],
                actor_email=profile["email"],
                document_id=payload.document["document_id"],
                source_id=source_id,
                project_id=project_id.strip(),
                worker_uid=worker_uid.strip(),
                chunks=chunk_payloads,
            )
            task_ids.append(_enqueue_knowledge_command(chunk_cmd))
            documents += 1
            chunks += len(chunk_payloads)

        ready_cmd = CreateKnowledgeSourceCommand(
            source_id=source_id,
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            project_id=project_id.strip(),
            worker_uid=worker_uid.strip(),
            source_kind="file",
            source_uri=f"upload://{source_id}",
            display_name=resolved_display,
            status="ready",
            metadata={
                "upload": True,
                "documents": documents,
                "chunks": chunks,
                "file_names": upload_labels,
            },
        )
        task_ids.append(_enqueue_knowledge_command(ready_cmd))
    except Exception as exc:
        raise problem(400, "No se pudo procesar la carga RAG", str(exc)) from exc

    return {
        "ok": True,
        "source_id": source_id,
        "task_ids": task_ids,
        "documents": documents,
        "chunks": chunks,
    }


@router.post("/knowledge/sources/{source_id}/sync", dependencies=[Depends(require_admin_key)])
async def sync_knowledge_source(
    source_id: str,
    body: KnowledgeSyncBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_knowledge_read import get_knowledge_source, list_source_document_checksums
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.forge.rag.knowledge_auto_sync import execute_folder_sync

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
        existing = list_source_document_checksums(db, source_id=source_id)

    try:
        outcome = execute_folder_sync(
            source=source,
            existing=existing,
            actor_email=profile["email"],
            compute_embeddings=body.compute_embeddings,
            force=True,
        )
    except Exception as exc:
        raise problem(400, str(exc), "knowledge_sync") from exc

    return {
        "ok": True,
        "source_id": source_id,
        "task_ids": outcome.task_ids,
        "scanned": outcome.scanned,
        "upserted": outcome.upserted,
        "skipped": outcome.skipped,
        "removed": outcome.removed,
        "chunks": outcome.chunks,
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
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.forge.rag.knowledge_core import search_knowledge as _search

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)
        rows = _search(
            db,
            query=body.query,
            tenant_id=profile["tenant_id"],
            project_id=body.project_id.strip(),
            worker_uid=body.worker_uid.strip(),
            source_id=body.source_id.strip(),
            limit=body.limit,
        )
    return {"results": rows, "count": len(rows)}
