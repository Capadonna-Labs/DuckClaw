from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/prompt-policies", tags=["admin-prompt-policies"])

WORKSPACE_MANAGED_DRAFT_POLICY_TYPE = "manager_task"
WORKSPACE_MANAGED_DRAFT_POLICY_NAME = "admin_workspace_managed_draft"

_PROMPT_POLICY_ALIASES = {
    "capabilities": "capability",
    "directives": "directive",
    "manager_tasks": "manager_task",
    "system_prompts": "system_prompt",
}
_PROMPT_POLICY_TYPES = {"directive", "capability", "system_prompt", "manager_task", "tool_directive"}
_PROMPT_POLICY_STATUSES = {"draft", "active", "inactive", "archived"}


class PromptPolicyUpsertBody(BaseModel):
    policy_type: str = Field(..., min_length=1, max_length=64)
    policy_name: str = Field(..., min_length=1, max_length=160)
    version: int = Field(default=1, ge=1)
    status: str = Field(default="active", max_length=32)
    content: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


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


def _fetchall(result: Any) -> list[Any]:
    if hasattr(result, "fetchall"):
        return list(result.fetchall())
    if isinstance(result, list):
        return result
    return []


def _normalize_prompt_policy_type(raw: str) -> str:
    value = str(raw or "").strip().lower()
    normalized = _PROMPT_POLICY_ALIASES.get(value, value)
    if normalized not in _PROMPT_POLICY_TYPES:
        raise ValueError(f"policy_type inválido: {raw}")
    return normalized


def _normalize_prompt_policy_status(raw: str) -> str:
    status_value = str(raw or "active").strip().lower()
    if status_value not in _PROMPT_POLICY_STATUSES:
        raise ValueError(f"status inválido: {raw}")
    return status_value


def _prompt_policy_id(policy_type: str, policy_name: str, version: int) -> str:
    digest = hashlib.sha256(f"{policy_type}:{policy_name}:{version}".encode("utf-8")).hexdigest()
    return f"ppol_{digest[:24]}"


def _prompt_policy_row(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        policy_id,
        policy_type,
        policy_name,
        version,
        status_value,
        content,
        checksum,
        metadata_json,
        active,
        created_at,
        updated_at,
    ) = row
    try:
        metadata = json.loads(metadata_json or "{}")
    except json.JSONDecodeError:
        metadata = {}
    return {
        "policy_id": str(policy_id),
        "policy_type": str(policy_type),
        "policy_name": str(policy_name),
        "version": int(version or 0),
        "status": str(status_value or ""),
        "content": str(content or ""),
        "checksum": str(checksum or ""),
        "metadata": metadata if isinstance(metadata, dict) else {},
        "active": bool(active),
        "created_at": str(created_at),
        "updated_at": str(updated_at),
    }


def _prompt_policy_requirement_row(requirement: Any) -> dict[str, str]:
    return {
        "policy_type": str(requirement.policy_type),
        "policy_name": str(requirement.policy_name),
        "source": str(requirement.source),
    }


def _enqueue_prompt_policy_command(command: Any) -> str:
    from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync
    from duckclaw.gateway_db import get_gateway_db_path

    task_id = enqueue_typed_command(command, db_path=get_gateway_db_path(), user_id="default")
    command_status = poll_task_status_sync(task_id, timeout_sec=0.5)
    if command_status and command_status.status == "failed":
        detail = command_status.detail or "prompt policy write failed"
        if "No hay query SQL" in detail:
            raise ValueError(
                "DB-Writer desactualizado: reinicia DuckClaw-DB-Writer y DuckClaw-Gateway para aplicar comandos de prompt policies."
            )
        raise ValueError(detail)
    return task_id


@router.get("", dependencies=[Depends(require_admin_key)])
async def list_prompt_policies(
    policy_type: str = "",
    policy_name: str = "",
    include_inactive: bool = False,
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db

    clauses: list[str] = []
    params: list[Any] = []
    try:
        if policy_type.strip():
            clauses.append("policy_type = ?")
            params.append(_normalize_prompt_policy_type(policy_type))
        if policy_name.strip():
            clauses.append("policy_name = ?")
            params.append(policy_name.strip())
        if not include_inactive:
            clauses.append("active = true")
            clauses.append("status = 'active'")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with open_gateway_db(read_only=True) as db:
            rows = _fetchall(
                db.execute(
                    "SELECT policy_id, policy_type, policy_name, version, status, content, checksum, "
                    "metadata_json, active, created_at, updated_at "
                    f"FROM main.prompt_policy_registry {where} "
                    "ORDER BY policy_type ASC, policy_name ASC, version DESC",
                    params,
                )
            )
    except ValueError as exc:
        raise _problem(400, str(exc), "prompt_policy") from exc
    except Exception as exc:
        raise _problem(
            400,
            "Prompt policy registry no disponible",
            "Ejecuta migración 16 antes de administrar prompt policies.",
        ) from exc
    return {"policies": [_prompt_policy_row(row) for row in rows]}


@router.get("/health", dependencies=[Depends(require_admin_key)])
async def prompt_policy_health(
    worker_id: list[str] | None = Query(None),
    include_framework: bool = True,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_worker_catalog import list_visible_workers_for_actor
    from duckclaw.prompt_policies import (
        missing_prompt_policies,
        prompt_policy_requirements_for_workers,
    )
    from duckclaw.workers.factory import list_workers

    try:
        with open_gateway_db(read_only=True) as db:
            requested_workers = [
                str(item or "").strip()
                for item in (worker_id or [])
                if str(item or "").strip()
            ]
            if requested_workers:
                workers = requested_workers
            elif actor and "@" in actor:
                workers = [
                    str(item.get("id") or item.get("worker_id") or "").strip()
                    for item in list_visible_workers_for_actor(db, actor_email=actor)
                    if str(item.get("id") or item.get("worker_id") or "").strip()
                ]
            else:
                workers = list_workers(db=db)
            requirements = prompt_policy_requirements_for_workers(
                workers,
                include_framework=include_framework,
            )
            missing = missing_prompt_policies(db, requirements)
    except Exception as exc:
        raise _problem(
            400,
            "Prompt policy health no disponible",
            "Ejecuta migración 16 antes de auditar prompt policies.",
        ) from exc
    return {
        "ok": not missing,
        "checked_count": len(requirements),
        "missing_count": len(missing),
        "requirements": [_prompt_policy_requirement_row(item) for item in requirements],
        "missing": [_prompt_policy_requirement_row(item) for item in missing],
    }


@router.put("", dependencies=[Depends(require_admin_key)])
async def upsert_prompt_policy(
    body: PromptPolicyUpsertBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.write_commands import UpsertPromptPolicyCommand

    try:
        policy_type = _normalize_prompt_policy_type(body.policy_type)
        status_value = _normalize_prompt_policy_status(body.status)
        policy_name = body.policy_name.strip()
        content = body.content
        if not content.strip():
            raise ValueError("content requerido")
        policy_id = _prompt_policy_id(policy_type, policy_name, body.version)
        command = UpsertPromptPolicyCommand(
            policy_id=policy_id,
            policy_type=policy_type,  # type: ignore[arg-type]
            policy_name=policy_name,
            version=body.version,
            status=status_value,  # type: ignore[arg-type]
            content=content,
            metadata=body.metadata,
            actor_email=actor,
        )
        task_id = _enqueue_prompt_policy_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), "prompt_policy") from exc
    return {
        "ok": True,
        "task_id": task_id,
        "policy": {
            "policy_id": policy_id,
            "policy_type": policy_type,
            "policy_name": policy_name,
            "version": body.version,
            "status": status_value,
            "active": status_value == "active",
        },
    }


@router.delete("/{policy_type}/{policy_name}", dependencies=[Depends(require_admin_key)])
async def deactivate_prompt_policy(
    policy_type: str,
    policy_name: str,
    version: int | None = Query(None, ge=1),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.write_commands import DeactivatePromptPolicyCommand

    try:
        normalized_type = _normalize_prompt_policy_type(policy_type)
        name = policy_name.strip()
        if not name:
            raise ValueError("policy_name requerido")
        command = DeactivatePromptPolicyCommand(
            policy_type=normalized_type,  # type: ignore[arg-type]
            policy_name=name,
            version=version,
            actor_email=actor,
        )
        task_id = _enqueue_prompt_policy_command(command)
    except ValueError as exc:
        raise _problem(404, str(exc), f"{policy_type}/{policy_name}") from exc
    return {
        "ok": True,
        "task_id": task_id,
        "policy_type": normalized_type,
        "policy_name": name,
        "version": version,
    }
