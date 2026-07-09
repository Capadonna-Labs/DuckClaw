from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from core.admin_identity import effective_actor_email, open_gateway_db
from duckclaw.admin_mcp_connectors import (
    get_mcp_connector,
    get_mcp_connector_runtime,
    list_mcp_connectors,
    resolve_worker_uid,
)
from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.gateway_enqueue import enqueue_admin_command
from duckclaw.mcp_connector_presets import list_mcp_connector_presets
from duckclaw.write_commands import (
    DeactivateMcpConnectorCommand,
    GrantWorkerMcpConnectorCommand,
    RevokeWorkerMcpConnectorCommand,
    SetMcpConnectorAuthCommand,
    UpsertMcpConnectorCommand,
)

router = APIRouter(prefix="/mcp/connectors", tags=["admin-mcp-connectors"])


class McpConnectorCreateBody(BaseModel):
    connector_id: str = ""
    preset_id: str = ""
    display_name: str = ""
    transport: str = ""
    endpoint_url: str = ""
    launch_command: str = ""
    launch_args: list[str] = Field(default_factory=list)
    auth_kind: str = "none"
    tool_allowlist: list[str] = Field(default_factory=list)
    tool_denylist: list[str] = Field(default_factory=list)
    read_only: bool | None = None
    egress_hosts: list[str] = Field(default_factory=list)
    enabled: bool = True


class McpConnectorPatchBody(BaseModel):
    display_name: str | None = None
    tool_allowlist: list[str] | None = None
    tool_denylist: list[str] | None = None
    read_only: bool | None = None
    enabled: bool | None = None


class McpConnectorAuthBody(BaseModel):
    bearer_token: str = Field(..., min_length=8)


class McpConnectorOAuthStartBody(BaseModel):
    redirect_uri: str = ""


class McpConnectorOAuthCompleteBody(BaseModel):
    code: str = Field(..., min_length=1)
    state: str = Field(..., min_length=8)


class McpConnectorGrantBody(BaseModel):
    worker_id: str = Field(..., min_length=1)


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    expected = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DUCKCLAW_ADMIN_API_KEY no configurada en el gateway",
        )
    if (x_admin_key or "").strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin key inválida")


def actor_from_header(x_actor: str | None = Header(None, alias="X-Duckclaw-Actor")) -> str:
    raw = (x_actor or "").strip()[:128]
    if raw and raw != "admin-ui":
        return raw
    admin_email = os.environ.get("DUCKCLAW_ADMIN_EMAIL", "").strip()
    if admin_email and "@" in admin_email:
        return admin_email[:128]
    return raw or "admin-ui"


def _problem(status_code: int, title: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"type": "about:blank", "title": title, "status": status_code, "detail": detail},
    )


def _actor_profile(actor: str) -> dict[str, Any]:
    actor_email = effective_actor_email(actor)
    with open_gateway_db(read_only=True) as db:
        return ensure_profile_for_user(db, email=actor_email)


def _enqueue(command: Any) -> str:
    return enqueue_admin_command(command)


@router.get("", dependencies=[Depends(require_admin_key)])
async def list_connectors(actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    profile = _actor_profile(actor)
    tenant_id = str(profile.get("tenant_id") or "default")
    with open_gateway_db(read_only=True) as db:
        connectors = list_mcp_connectors(db, tenant_id=tenant_id)
    return {"connectors": connectors}


@router.get("/presets", dependencies=[Depends(require_admin_key)])
async def list_presets() -> dict[str, Any]:
    return {"presets": list_mcp_connector_presets()}


@router.post("", dependencies=[Depends(require_admin_key)])
async def create_connector(body: McpConnectorCreateBody, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    profile = _actor_profile(actor)
    tenant_id = str(profile.get("tenant_id") or "default")
    actor_email = str(profile.get("email") or actor)
    connector_id = body.connector_id.strip() or (f"mcp_{body.preset_id.strip()}" if body.preset_id.strip() else "")
    command = UpsertMcpConnectorCommand(
        tenant_id=tenant_id,
        actor_email=actor_email,
        connector_id=connector_id,
        preset_id=body.preset_id.strip(),
        display_name=body.display_name.strip(),
        transport=body.transport.strip(),
        endpoint_url=body.endpoint_url.strip(),
        launch_command=body.launch_command.strip(),
        launch_args=body.launch_args,
        auth_kind=body.auth_kind.strip() if body.auth_kind.strip() not in ("", "none") else "",
        tool_allowlist=body.tool_allowlist,
        tool_denylist=body.tool_denylist,
        read_only=body.read_only,
        egress_hosts=body.egress_hosts,
        enabled=body.enabled,
    )
    try:
        task_id = _enqueue(command)
    except ValueError as exc:
        raise _problem(400, str(exc), body.preset_id or body.connector_id) from exc
    connector_id = body.connector_id.strip() or (f"mcp_{body.preset_id.strip()}" if body.preset_id.strip() else "")
    with open_gateway_db(read_only=True) as db:
        connector = get_mcp_connector(db, connector_id=connector_id, tenant_id=tenant_id)
        if connector is None:
            rows = list_mcp_connectors(db, tenant_id=tenant_id)
            connector = rows[-1] if rows else None
    return {"ok": True, "task_id": task_id, "connector": connector}


@router.patch("/{connector_id}", dependencies=[Depends(require_admin_key)])
async def patch_connector(
    connector_id: str,
    body: McpConnectorPatchBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    profile = _actor_profile(actor)
    tenant_id = str(profile.get("tenant_id") or "default")
    with open_gateway_db(read_only=True) as db:
        existing = get_mcp_connector_runtime(db, connector_id=connector_id, tenant_id=tenant_id)
    if not existing:
        raise _problem(404, "Conector no encontrado", connector_id)
    command = UpsertMcpConnectorCommand(
        tenant_id=tenant_id,
        actor_email=str(profile.get("email") or actor),
        connector_id=connector_id,
        display_name=(body.display_name or existing.get("display_name") or connector_id),
        transport=str(existing.get("transport") or ""),
        endpoint_url=str(existing.get("endpoint_url") or ""),
        launch_command=str(existing.get("launch_command") or ""),
        launch_args=list(existing.get("launch_args") or []),
        auth_kind=str(existing.get("auth_kind") or "none"),
        tool_allowlist=body.tool_allowlist if body.tool_allowlist is not None else list(existing.get("tool_allowlist") or []),
        tool_denylist=body.tool_denylist if body.tool_denylist is not None else list(existing.get("tool_denylist") or []),
        read_only=body.read_only if body.read_only is not None else bool(existing.get("read_only", True)),
        egress_hosts=list(existing.get("egress_hosts") or []),
        preset_id=str(existing.get("preset_id") or ""),
        enabled=body.enabled if body.enabled is not None else bool(existing.get("enabled", True)),
        metadata=dict(existing.get("metadata") or {}),
    )
    try:
        task_id = _enqueue(command)
    except ValueError as exc:
        raise _problem(400, str(exc), connector_id) from exc
    with open_gateway_db(read_only=True) as db:
        connector = get_mcp_connector(db, connector_id=connector_id, tenant_id=tenant_id)
    return {"ok": True, "task_id": task_id, "connector": connector}


@router.post("/{connector_id}/auth", dependencies=[Depends(require_admin_key)])
async def set_connector_auth(
    connector_id: str,
    body: McpConnectorAuthBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    profile = _actor_profile(actor)
    tenant_id = str(profile.get("tenant_id") or "default")
    command = SetMcpConnectorAuthCommand(
        tenant_id=tenant_id,
        actor_email=str(profile.get("email") or actor),
        connector_id=connector_id,
        bearer_token=body.bearer_token.strip(),
    )
    try:
        task_id = _enqueue(command)
    except ValueError as exc:
        raise _problem(400, str(exc), connector_id) from exc
    return {"ok": True, "task_id": task_id}


@router.post("/{connector_id}/oauth/start", dependencies=[Depends(require_admin_key)])
async def start_connector_oauth(
    connector_id: str,
    body: McpConnectorOAuthStartBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    profile = _actor_profile(actor)
    tenant_id = str(profile.get("tenant_id") or "default")
    actor_email = str(profile.get("email") or actor)
    try:
        from duckclaw.mcp_higgsfield_oauth import start_higgsfield_oauth

        with open_gateway_db(read_only=True) as db:
            result = await start_higgsfield_oauth(
                db,
                connector_id=connector_id,
                tenant_id=tenant_id,
                actor_email=actor_email,
                redirect_uri=body.redirect_uri.strip() or None,
            )
        return {"ok": True, **result}
    except ValueError as exc:
        raise _problem(400, "OAuth start failed", str(exc)) from exc
    except Exception as exc:
        raise _problem(502, "OAuth start failed", str(exc)) from exc


@router.post("/oauth/complete", dependencies=[Depends(require_admin_key)])
async def complete_connector_oauth(
    body: McpConnectorOAuthCompleteBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    del actor
    try:
        from duckclaw.mcp_higgsfield_oauth import (
            build_oauth_completion_commands,
            exchange_oauth_code_for_token,
        )
        from duckclaw.write_commands import SetMcpConnectorAuthCommand

        bundle = build_oauth_completion_commands(code=body.code.strip(), state=body.state.strip())
        pending = bundle["pending"]
        tokens = await exchange_oauth_code_for_token(code=body.code.strip(), pending=pending)
        command = SetMcpConnectorAuthCommand(
            tenant_id=str(pending.get("tenant_id") or "default"),
            actor_email=str(pending.get("actor_email") or "system"),
            connector_id=str(pending.get("connector_id") or ""),
            bearer_token=tokens["access_token"],
        )
        task_id = _enqueue(command)
        return {"ok": True, "task_id": task_id, "connector_id": command.connector_id}
    except ValueError as exc:
        raise _problem(400, "OAuth complete failed", str(exc)) from exc
    except Exception as exc:
        raise _problem(502, "OAuth complete failed", str(exc)) from exc


@router.get("/oauth/callback")
async def oauth_callback_public(
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
) -> RedirectResponse:
    """Browser redirect from Higgsfield; exchanges code and redirects to Admin UI."""
    import logging

    _log = logging.getLogger(__name__)
    admin_base = (os.environ.get("DUCKCLAW_ADMIN_URL") or "").strip().rstrip("/")
    if not admin_base or "0.0.0.0" in admin_base:
        host = (os.environ.get("DUCKCLAW_ADMIN_PUBLIC_HOST") or "").strip()
        if host:
            admin_base = f"https://{host}".rstrip("/")
        else:
            admin_base = "http://127.0.0.1:3000"
    fail = f"{admin_base}/mcp?tab=connectors&oauth=error"
    ok = f"{admin_base}/mcp?tab=connectors&oauth=success"
    if error:
        msg = (error_description or error).strip()[:120]
        return RedirectResponse(url=f"{fail}&msg={msg}", status_code=302)
    if not code.strip() or not state.strip():
        return RedirectResponse(url=f"{fail}&msg=missing_code_or_state", status_code=302)
    try:
        from duckclaw.mcp_higgsfield_oauth import (
            build_oauth_completion_commands,
            exchange_oauth_code_for_token,
        )
        from duckclaw.write_commands import SetMcpConnectorAuthCommand

        bundle = build_oauth_completion_commands(code=code.strip(), state=state.strip())
        pending = bundle["pending"]
        tokens = await exchange_oauth_code_for_token(code=code.strip(), pending=pending)
        command = SetMcpConnectorAuthCommand(
            tenant_id=str(pending.get("tenant_id") or "default"),
            actor_email=str(pending.get("actor_email") or "system"),
            connector_id=str(pending.get("connector_id") or ""),
            bearer_token=tokens["access_token"],
        )
        _enqueue(command)
        return RedirectResponse(url=ok, status_code=302)
    except Exception as exc:
        _log.warning("MCP OAuth callback failed: %s", exc)
        msg = str(exc).strip()[:120]
        return RedirectResponse(url=f"{fail}&msg={msg}", status_code=302)


@router.post("/{connector_id}/test", dependencies=[Depends(require_admin_key)])
async def test_connector(connector_id: str, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    profile = _actor_profile(actor)
    tenant_id = str(profile.get("tenant_id") or "default")
    with open_gateway_db(read_only=True) as db:
        connector = get_mcp_connector_runtime(db, connector_id=connector_id, tenant_id=tenant_id)
        if not connector:
            raise _problem(404, "Conector no encontrado", connector_id)
        try:
            from duckclaw.forge.skills.mcp_connector_bridge import test_mcp_connector

            return await test_mcp_connector(db, connector)
        except Exception as exc:
            raise _problem(502, "Test MCP falló", str(exc)) from exc


@router.post("/{connector_id}/grants", dependencies=[Depends(require_admin_key)])
async def grant_connector(
    connector_id: str,
    body: McpConnectorGrantBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    profile = _actor_profile(actor)
    tenant_id = str(profile.get("tenant_id") or "default")
    with open_gateway_db(read_only=True) as db:
        worker_uid = resolve_worker_uid(db, worker_id=body.worker_id.strip(), tenant_id=tenant_id)
    if not worker_uid:
        raise _problem(404, "Worker no encontrado", body.worker_id)
    command = GrantWorkerMcpConnectorCommand(
        tenant_id=tenant_id,
        actor_email=str(profile.get("email") or actor),
        connector_id=connector_id,
        worker_uid=worker_uid,
    )
    try:
        task_id = _enqueue(command)
    except ValueError as exc:
        raise _problem(400, str(exc), connector_id) from exc
    return {"ok": True, "task_id": task_id, "worker_id": body.worker_id, "worker_uid": worker_uid}


@router.delete("/{connector_id}/grants/{worker_id}", dependencies=[Depends(require_admin_key)])
async def revoke_connector_grant(
    connector_id: str,
    worker_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    profile = _actor_profile(actor)
    tenant_id = str(profile.get("tenant_id") or "default")
    with open_gateway_db(read_only=True) as db:
        worker_uid = resolve_worker_uid(db, worker_id=worker_id.strip(), tenant_id=tenant_id)
    if not worker_uid:
        raise _problem(404, "Worker no encontrado", worker_id)
    command = RevokeWorkerMcpConnectorCommand(
        tenant_id=tenant_id,
        actor_email=str(profile.get("email") or actor),
        connector_id=connector_id,
        worker_uid=worker_uid,
    )
    try:
        task_id = _enqueue(command)
    except ValueError as exc:
        raise _problem(400, str(exc), connector_id) from exc
    return {"ok": True, "task_id": task_id}


@router.delete("/{connector_id}", dependencies=[Depends(require_admin_key)])
async def deactivate_connector(connector_id: str, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    profile = _actor_profile(actor)
    tenant_id = str(profile.get("tenant_id") or "default")
    command = DeactivateMcpConnectorCommand(
        tenant_id=tenant_id,
        actor_email=str(profile.get("email") or actor),
        connector_id=connector_id,
    )
    try:
        task_id = _enqueue(command)
    except ValueError as exc:
        raise _problem(400, str(exc), connector_id) from exc
    return {"ok": True, "task_id": task_id}
