"""RAG / knowledge admin routes (sources, uploads, search)."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import (
    actor_from_header,
    problem,
    require_admin_key,
)

router = APIRouter(tags=["admin-knowledge"])

_KNOWLEDGE_UPLOAD_MAX_FILES = 40
_KNOWLEDGE_UPLOAD_MAX_BYTES = 5 * 1024 * 1024


class KnowledgeSourceCreateBody(BaseModel):
    source_uri: str = Field(..., min_length=1, max_length=4096)
    display_name: str = Field(default="", max_length=160)
    source_kind: str = Field(default="folder", max_length=32)
    project_id: str = Field(default="", max_length=128)
    worker_uid: str = Field(default="", max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)
    ingest: bool = True
    compute_embeddings: bool = False


class KnowledgeSearchBody(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    project_id: str = Field(default="", max_length=128)
    worker_uid: str = Field(default="", max_length=128)
    source_id: str = Field(default="", max_length=128)
    limit: int = 8


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


def _knowledge_allowed_roots() -> list[Path]:
    roots: list[Path] = []
    raw = (os.environ.get("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS") or "").strip()
    for item in raw.split(os.pathsep):
        if item.strip():
            roots.append(Path(item).expanduser().resolve())
    repo = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    if repo:
        roots.append(Path(repo).expanduser().resolve())
    return roots


def _validate_knowledge_ingest_root(source_uri: str) -> Path:
    target = Path(source_uri).expanduser().resolve()
    if not target.exists():
        raise ValueError(f"Ruta de conocimiento no existe: {source_uri}")
    allowed = _knowledge_allowed_roots()
    if not allowed:
        raise ValueError("DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS no configurado para ingesta local")
    if not any(target == root or root in target.parents for root in allowed):
        raise ValueError("Ruta de conocimiento fuera de raíces permitidas")
    return target


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


@router.post("/knowledge/sources", dependencies=[Depends(require_admin_key)])
async def create_knowledge_source(
    body: KnowledgeSourceCreateBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.forge.rag.knowledge_core import build_document_payload, embed_chunk_payloads, iter_allowed_files
    from duckclaw.write_commands import (
        CreateKnowledgeSourceCommand,
        UpsertKnowledgeChunksCommand,
        UpsertKnowledgeDocumentCommand,
    )

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
        if body.ingest:
            root = _validate_knowledge_ingest_root(body.source_uri)
            files = iter_allowed_files(root)
            embedding_fn = None
            if body.compute_embeddings:
                from duckclaw.forge.rag.embeddings import embed_text

                embedding_fn = embed_text
            for file_path in files:
                payload = build_document_payload(
                    root=root if root.is_dir() else root.parent,
                    path=file_path,
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
                    project_id=body.project_id.strip(),
                    worker_uid=body.worker_uid.strip(),
                    chunks=chunk_payloads,
                )
                task_ids.append(_enqueue_knowledge_command(chunk_cmd))
                documents += 1
                chunks += len(chunk_payloads)
            ready_cmd = CreateKnowledgeSourceCommand(
                source_id=source_id,
                tenant_id=profile["tenant_id"],
                actor_email=profile["email"],
                project_id=body.project_id.strip(),
                worker_uid=body.worker_uid.strip(),
                source_kind=body.source_kind.strip() or "folder",  # type: ignore[arg-type]
                source_uri=body.source_uri.strip(),
                display_name=body.display_name.strip(),
                status="ready",
                metadata={**body.metadata, "documents": documents, "chunks": chunks},
            )
            task_ids.append(_enqueue_knowledge_command(ready_cmd))
    except Exception as exc:
        raise problem(400, str(exc), "knowledge_source") from exc

    return {
        "ok": True,
        "source_id": source_id,
        "task_ids": task_ids,
        "documents": documents,
        "chunks": chunks,
    }


@router.post("/knowledge/uploads", dependencies=[Depends(require_admin_key)])
async def upload_knowledge_files(
    project_id: str = Form(default=""),
    worker_uid: str = Form(default=""),
    display_name: str = Form(default=""),
    compute_embeddings: bool = Form(default=False),
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
        source_cmd = CreateKnowledgeSourceCommand(
            source_id=source_id,
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            project_id=project_id.strip(),
            worker_uid=worker_uid.strip(),
            source_kind="file",
            source_uri=f"upload://{source_id}",
            display_name=(display_name or "").strip() or "Carga de archivos",
            status="indexing",
            metadata={"upload": True, "file_count": len(files)},
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
            display_name=(display_name or "").strip() or "Carga de archivos",
            status="ready",
            metadata={"upload": True, "documents": documents, "chunks": chunks},
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
