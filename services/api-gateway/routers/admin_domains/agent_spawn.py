"""Admin routes for A2A Agent Card export and spawn package import."""

from __future__ import annotations

import io
import json
import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.admin_identity import effective_actor_email, open_gateway_db
from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.admin_worker_catalog import (
    get_visible_worker_for_actor,
    get_worker_by_tenant_worker_id,
    set_worker_a2a_discoverable,
)
from duckclaw.agent_card_builder import build_a2a_agent_card_from_db
from duckclaw.spawn_package_builder import analyze_spawn_package_from_bytes, build_spawn_package_bytes
from duckclaw.spawn_package_import import import_spawn_package_to_catalog
from routers.admin_domains.admin_common import actor_from_header, problem, require_admin_key

router = APIRouter(prefix="/agents", tags=["admin-agent-spawn"])


class A2aDiscoverableBody(BaseModel):
    discoverable: bool = False


class SpawnImportOptions(BaseModel):
    confirm_high_risk: bool = False
    worker_id_override: str | None = Field(default=None, max_length=64)


def _sanitize_worker_id(worker_id: str) -> str:
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", (worker_id or "").strip())
    if not wid:
        raise problem(400, "worker_id inválido", worker_id or "")
    return wid


def _resolve_worker_access(worker_id: str, actor: str) -> tuple[str, dict[str, Any] | None]:
    wid = _sanitize_worker_id(worker_id)
    actor_email = effective_actor_email(actor)
    tenant_id = "default"
    with open_gateway_db(read_only=True) as db:
        if "@" in actor_email:
            visible = get_visible_worker_for_actor(db, actor_email=actor_email, worker_id=wid)
            if visible:
                tenant_id = str(visible.get("tenant_id") or "default")
            elif wid != "default":
                raise problem(404, "Worker no visible", wid)
        cat = get_worker_by_tenant_worker_id(db, tenant_id=tenant_id, worker_id=wid)
    return tenant_id, cat


def _runtime_tool_names() -> list[str]:
    try:
        from routers.admin_domains.worker_capabilities import build_worker_capabilities_payload

        payload = build_worker_capabilities_payload("default", actor="admin-ui")
        return [str(t).strip().lower() for t in payload.get("tools_runtime") or [] if str(t).strip()]
    except Exception:
        pack_tools = ["read_sql", "inspect_schema", "get_db_path", "admin_sql"]
        return pack_tools


def _admin_audit(action: str, resource: str, detail: str, *, actor: str) -> None:
    from routers import admin as admin_router

    admin_router._admin_audit(action, resource, detail, actor=actor)


@router.get("/{worker_id}/agent-card", dependencies=[Depends(require_admin_key)])
async def admin_agent_card(
    worker_id: str,
    actor: str = Depends(actor_from_header),
) -> JSONResponse:
    tenant_id, _cat = _resolve_worker_access(worker_id, actor)
    wid = _sanitize_worker_id(worker_id)
    with open_gateway_db(read_only=True) as db:
        try:
            card = build_a2a_agent_card_from_db(db, wid, tenant_id=tenant_id)
        except FileNotFoundError as exc:
            raise problem(404, "Worker no encontrado", str(exc)) from exc
    return JSONResponse(
        content=card,
        headers={
            "Content-Disposition": f'attachment; filename="{wid}-agent-card.json"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{worker_id}/spawn-package", dependencies=[Depends(require_admin_key)])
async def download_spawn_package(
    worker_id: str,
    actor: str = Depends(actor_from_header),
) -> StreamingResponse:
    tenant_id, _cat = _resolve_worker_access(worker_id, actor)
    wid = _sanitize_worker_id(worker_id)
    with open_gateway_db(read_only=True) as db:
        try:
            data = build_spawn_package_bytes(db, wid, tenant_id=tenant_id)
        except ValueError as exc:
            raise problem(403, "Export bloqueado", str(exc)) from exc
        except FileNotFoundError as exc:
            raise problem(404, "Worker no encontrado", str(exc)) from exc
    _admin_audit("spawn_export", wid, "spawn package downloaded", actor=actor)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{wid}-spawn-package.zip"',
            "Cache-Control": "no-store",
        },
    )


@router.patch("/{worker_id}/a2a-discoverable", dependencies=[Depends(require_admin_key)])
async def patch_a2a_discoverable(
    worker_id: str,
    body: A2aDiscoverableBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    tenant_id, cat = _resolve_worker_access(worker_id, actor)
    wid = _sanitize_worker_id(worker_id)
    if not cat and wid == "default":
        raise problem(400, "default worker no está en catálogo", wid)
    with open_gateway_db(read_only=False) as db:
        cat = get_worker_by_tenant_worker_id(db, tenant_id=tenant_id, worker_id=wid)
        if not cat:
            raise problem(404, "Worker no encontrado", wid)
        set_worker_a2a_discoverable(
            db, worker_uid=str(cat["worker_uid"]), discoverable=body.discoverable
        )
    _admin_audit(
        "a2a_discoverable",
        wid,
        f"discoverable={body.discoverable}",
        actor=actor,
    )
    return {"ok": True, "worker_id": wid, "a2a_discoverable": body.discoverable}


@router.post("/spawn-package/preview", dependencies=[Depends(require_admin_key)])
async def preview_spawn_package(
    file: UploadFile = File(...),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    del actor
    raw = await file.read()
    if not raw:
        raise problem(400, "Archivo vacío", "spawn-package")
    try:
        analysis, manifest, _files = analyze_spawn_package_from_bytes(
            raw, available_tools=_runtime_tool_names()
        )
    except ValueError as exc:
        raise problem(400, "Paquete inválido", str(exc)) from exc
    if analysis.secret_findings:
        raise problem(403, "Secretos detectados en paquete", ", ".join(analysis.secret_findings[:5]))
    return {"ok": True, "preview": analysis.to_dict(), "manifest_id": manifest.get("id")}


@router.post("/spawn-package/import", dependencies=[Depends(require_admin_key)])
async def import_spawn_package(
    file: UploadFile = File(...),
    options_json: str = Form(default="{}"),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    raw = await file.read()
    if not raw:
        raise problem(400, "Archivo vacío", "spawn-package")
    try:
        opts = SpawnImportOptions.model_validate(json.loads(options_json or "{}"))
    except Exception as exc:
        raise problem(400, "options_json inválido", str(exc)) from exc

    try:
        analysis, manifest, files = analyze_spawn_package_from_bytes(
            raw, available_tools=_runtime_tool_names()
        )
    except ValueError as exc:
        raise problem(400, "Paquete inválido", str(exc)) from exc

    if analysis.secret_findings:
        raise problem(403, "Secretos detectados en paquete", ", ".join(analysis.secret_findings[:5]))

    if analysis.import_blocked_until_confirm and not opts.confirm_high_risk:
        raise HTTPException(
            status_code=409,
            detail={
                "type": "about:blank",
                "title": "Confirmación requerida",
                "status": 409,
                "detail": "El paquete solicita tools de alto riesgo",
                "high_risk_findings": analysis.high_risk_findings,
            },
        )

    actor_email = effective_actor_email(actor)
    with open_gateway_db(read_only=False) as db:
        profile = ensure_profile_for_user(db, email=actor_email)
        result = import_spawn_package_to_catalog(
            db,
            owner_email=profile["email"],
            manifest=manifest,
            files=files,
            worker_id_override=opts.worker_id_override,
            force_read_only=True,
        )

    _admin_audit(
        "spawn_import",
        str(result.get("worker_id") or ""),
        f"confirm_high_risk={opts.confirm_high_risk} findings={analysis.high_risk_findings}",
        actor=actor,
    )
    return {"ok": True, "result": result, "preview": analysis.to_dict()}
