from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

import duckclaw.db_write_queue as db_write_queue
from core.admin_identity import effective_actor_email, open_gateway_db
from duckclaw.admin_user_agents import list_user_agents, sanitize_worker_id
from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.admin_worker_catalog import sanitize_catalog_worker_id
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.write_commands import UpsertUserAgentCommand

router = APIRouter(tags=["admin-user-agents"])


class UserAgentCreateBody(BaseModel):
    worker_id: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)
    source_template_id: str = "default"
    system_prompt: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    soul: str = ""
    tool_profile: str = "general"
    browser_sandbox: bool = False
    web_search: bool = False


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
    if "@" not in actor_email:
        raise _problem(401, "Actor autenticado requerido", actor or "")
    with open_gateway_db(read_only=True) as db:
        return ensure_profile_for_user(db, email=actor_email)


def _public_agent_from_db(actor_email: str, worker_id: str) -> dict[str, Any] | None:
    with open_gateway_db(read_only=True) as db:
        for agent in list_user_agents(db, actor_email):
            if str(agent.get("worker_id") or "") == worker_id:
                return dict(agent)
    return None


def _fallback_agent(
    profile: dict[str, Any],
    *,
    worker_id: str,
    display_name: str,
    source_template_id: str,
    worker_uid: str,
) -> dict[str, Any]:
    return {
        "tenant_id": str(profile.get("tenant_id") or "default"),
        "owner_email": str(profile.get("email") or ""),
        "worker_id": worker_id,
        "display_name": display_name,
        "source_template_id": source_template_id,
        "manifest_path": f"db://admin_worker_catalog/{worker_uid}/manifest.json",
        "active": True,
        "created_at": "",
        "updated_at": "",
    }


def _enqueue_user_agent_command(command: UpsertUserAgentCommand) -> str:
    task_id = db_write_queue.enqueue_typed_command(command, db_path=get_gateway_db_path(), user_id="default")
    command_status = db_write_queue.poll_task_status_sync(task_id, timeout_sec=0.5)
    if command_status and command_status.status == "failed":
        raise ValueError(command_status.detail or "user agent write failed")
    return task_id


@router.post("/user-agents", dependencies=[Depends(require_admin_key)])
async def create_user_agent(
    body: UserAgentCreateBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    profile = _actor_profile(actor)
    worker_id = sanitize_catalog_worker_id(sanitize_worker_id(body.worker_id))
    worker_uid = f"wrk_{uuid.uuid4().hex}"
    display_name = (body.display_name or worker_id).strip()
    source_template_id = (body.source_template_id or "default").strip() or "default"
    command = UpsertUserAgentCommand(
        tenant_id=str(profile.get("tenant_id") or "default"),
        actor_email=str(profile.get("email") or actor),
        worker_uid=worker_uid,
        worker_id=worker_id,
        display_name=display_name,
        source_template_id=source_template_id,
        system_prompt=body.system_prompt,
        description=body.description,
        skills=body.skills,
        soul=body.soul,
        tool_profile=body.tool_profile,
        browser_sandbox=body.browser_sandbox,
        web_search=body.web_search,
    )
    try:
        task_id = _enqueue_user_agent_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), worker_id) from exc

    agent = _public_agent_from_db(str(profile.get("email") or actor), worker_id) or _fallback_agent(
        profile,
        worker_id=worker_id,
        display_name=display_name,
        source_template_id=source_template_id,
        worker_uid=worker_uid,
    )
    return {"ok": True, "task_id": task_id, "agent": agent}
