from __future__ import annotations

import io
from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/sandbox/artifacts", tags=["admin-sandbox-artifacts"])


class PromoteArtifactBody(BaseModel):
    chat_id: str = Field(default="", max_length=128)
    relative_dest: str = Field(default="", max_length=512)
    sync_rag: bool = True
    tenant_id: str | None = Field(default=None, max_length=64)
    project_id: str | None = Field(default=None, max_length=64)


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    from routers import admin as admin_router

    admin_router._require_admin_key(x_admin_key)


def _problem(status_code: int, title: str, detail: str):
    from routers import admin as admin_router

    return admin_router._problem(status_code, title, detail)


def _authorize_playground(*, chat_id: str, tenant_id: str | None) -> None:
    from routers import admin as admin_router

    team_ctx = admin_router._playground_team_context(tenant_id=tenant_id, chat_id=chat_id)
    if not team_ctx.get("authorized"):
        raise _problem(403, "No autorizado", str(team_ctx.get("team_hint") or ""))


@router.get("/runs", dependencies=[Depends(require_admin_key)])
async def list_sandbox_artifact_runs(
    chat_id: str | None = Query(None, max_length=128),
    limit: int = Query(20, ge=1, le=100),
    tenant_id: str | None = Query(None, max_length=64),
) -> dict[str, Any]:
    """Lista runs sandbox: por chat o global (sin chat_id)."""
    from duckclaw.sandbox_artifacts import list_all_runs, list_runs_for_chat, sanitize_chat_to_session_id

    cid = (chat_id or "").strip()
    if cid:
        _authorize_playground(chat_id=cid, tenant_id=tenant_id)
        runs = list_runs_for_chat(cid, limit=limit)
        return {
            "chat_id": cid,
            "chat_session_id": sanitize_chat_to_session_id(cid),
            "runs": runs,
            "count": len(runs),
            "scope": "chat",
        }
    runs = list_all_runs(limit=limit)
    return {"chat_id": None, "runs": runs, "count": len(runs), "scope": "global"}


@router.get("/runs/{run_id}", dependencies=[Depends(require_admin_key)])
async def get_sandbox_artifact_run(
    run_id: str,
    chat_id: str = Query(..., min_length=1, max_length=128),
    tenant_id: str | None = Query(None, max_length=64),
) -> dict[str, Any]:
    """Detalle de un run sandbox (manifest completo)."""
    from duckclaw.sandbox_artifacts import RunNotFoundError, get_run_detail

    _authorize_playground(chat_id=chat_id.strip(), tenant_id=tenant_id)
    try:
        manifest = get_run_detail(chat_id.strip(), run_id)
    except RunNotFoundError as exc:
        raise _problem(404, "Run no encontrado", str(exc)) from exc
    return {"run": manifest}


@router.delete("/runs/{run_id}", dependencies=[Depends(require_admin_key)])
async def delete_sandbox_run(
    run_id: str,
    chat_id: str = Query(..., min_length=1, max_length=128),
    tenant_id: str | None = Query(None, max_length=64),
) -> dict[str, Any]:
    """Elimina un run sandbox completo."""
    from duckclaw.sandbox_artifacts import RunNotFoundError, delete_run

    _authorize_playground(chat_id=chat_id.strip(), tenant_id=tenant_id)
    try:
        return delete_run(run_id, chat_id.strip())
    except RunNotFoundError as exc:
        raise _problem(404, "Run no encontrado", str(exc)) from exc


@router.get("/{artifact_id}/preview", dependencies=[Depends(require_admin_key)])
async def preview_sandbox_artifact(
    artifact_id: str,
    chat_id: str = Query("", max_length=128),
    tenant_id: str | None = Query(None, max_length=64),
):
    """Preview de artefacto: JSON para texto/tabular o stream para imágenes."""
    from duckclaw.sandbox_artifacts import (
        ArtifactNotFoundError,
        PreviewNotSupportedError,
        _resolve_artifact_lookup,
        preview_content,
    )

    cid = (chat_id or "").strip()
    if cid:
        _authorize_playground(chat_id=cid, tenant_id=tenant_id)
    try:
        manifest, entry, file_path = _resolve_artifact_lookup(artifact_id, cid)
    except ArtifactNotFoundError as exc:
        raise _problem(404, "Artefacto no encontrado", str(exc)) from exc

    mime = str(entry.get("mime") or "")
    filename = str(entry.get("filename") or file_path.name)
    try:
        result = preview_content(file_path, mime=mime, filename=filename)
    except PreviewNotSupportedError as exc:
        raise _problem(404, "Preview no disponible", str(exc)) from exc

    if result.kind == "binary":
        return StreamingResponse(
            io.BytesIO(result.data),
            media_type=result.mime,
            headers={"Cache-Control": "no-store"},
        )

    payload = dict(result.payload or {})
    payload.setdefault("artifact_id", entry.get("artifact_id"))
    payload.setdefault("filename", filename)
    payload.setdefault("mime", mime)
    payload.setdefault("run_id", manifest.get("run_id"))
    payload.setdefault("chat_id", manifest.get("chat_id"))
    return JSONResponse(content=payload)


@router.get("/{artifact_id}/download", dependencies=[Depends(require_admin_key)])
async def download_sandbox_artifact(
    artifact_id: str,
    chat_id: str = Query("", max_length=128),
    tenant_id: str | None = Query(None, max_length=64),
) -> FileResponse:
    """Descarga binaria de un artefacto sandbox."""
    from duckclaw.sandbox_artifacts import ArtifactNotFoundError, _resolve_artifact_lookup

    cid = (chat_id or "").strip()
    if cid:
        _authorize_playground(chat_id=cid, tenant_id=tenant_id)
    try:
        _manifest, entry, file_path = _resolve_artifact_lookup(artifact_id, cid)
    except ArtifactNotFoundError as exc:
        raise _problem(404, "Artefacto no encontrado", str(exc)) from exc

    mime = str(entry.get("mime") or "application/octet-stream")
    filename = str(entry.get("filename") or file_path.name)
    return FileResponse(
        path=str(file_path),
        media_type=mime,
        filename=filename,
        headers={"Cache-Control": "no-store"},
    )


@router.delete("/{artifact_id}", dependencies=[Depends(require_admin_key)])
async def delete_sandbox_artifact(
    artifact_id: str,
    chat_id: str = Query("", max_length=128),
    tenant_id: str | None = Query(None, max_length=64),
) -> dict[str, Any]:
    """Elimina un artefacto del scratch sandbox."""
    from duckclaw.sandbox_artifacts import ArtifactNotFoundError, delete_artifact

    cid = (chat_id or "").strip()
    if cid:
        _authorize_playground(chat_id=cid, tenant_id=tenant_id)
    try:
        return delete_artifact(artifact_id, cid)
    except ArtifactNotFoundError as exc:
        raise _problem(404, "Artefacto no encontrado", str(exc)) from exc


@router.post("/{artifact_id}/save-to-vault", dependencies=[Depends(require_admin_key)])
async def save_sandbox_artifact_to_vault(
    artifact_id: str,
    body: PromoteArtifactBody,
) -> dict[str, Any]:
    """Copia artefacto a KNOWLEDGE_OUTPUT (Drive). RAG sync opcional."""
    from duckclaw.sandbox_artifacts import ArtifactNotFoundError, promote_artifact_to_output

    cid = (body.chat_id or "").strip()
    if cid:
        _authorize_playground(chat_id=cid, tenant_id=body.tenant_id)
    try:
        return promote_artifact_to_output(
            artifact_id,
            cid,
            relative_dest=body.relative_dest,
            sync_rag=body.sync_rag,
            tenant_id=(body.tenant_id or "default").strip() or "default",
            project_id=(body.project_id or "").strip(),
        )
    except ArtifactNotFoundError as exc:
        raise _problem(404, "Artefacto no encontrado", str(exc)) from exc
    except ValueError as exc:
        raise _problem(400, "No se pudo guardar", str(exc)) from exc


@router.post("/cleanup", dependencies=[Depends(require_admin_key)])
async def cleanup_sandbox_artifacts() -> dict[str, Any]:
    """Purga runs sandbox expirados (TTL)."""
    from duckclaw.sandbox_artifacts import purge_expired_runs

    return purge_expired_runs()
