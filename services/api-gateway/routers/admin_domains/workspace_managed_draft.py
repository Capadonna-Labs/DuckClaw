from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from core.admin_identity import effective_actor_email, open_gateway_db
from core.models import ChatRequest
from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.admin_worker_catalog import ensure_admin_worker_catalog_schema, sanitize_catalog_worker_id
from duckclaw.channels import GatewayDeliveryContext
from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.prompt_policies import PromptPolicyResolver
from duckclaw.write_commands import ConfirmWorkspaceManagedDraftCommand
from routers.admin_domains.playground.llm_settings import resolved_llm_for_playground
from routers.admin_domains.prompt_policies import (
    WORKSPACE_MANAGED_DRAFT_POLICY_NAME,
    WORKSPACE_MANAGED_DRAFT_POLICY_TYPE,
)

router = APIRouter(tags=["admin-workspace-managed-draft"])


class WorkspaceManagedDraftBody(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=4000)


class WorkspaceManagedDraftProjectBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(default="", max_length=2048)


class WorkspaceManagedDraftWorkerBody(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    role: str = Field(default="member", max_length=64)
    system_prompt: str = Field(default="", max_length=8000)


class WorkspaceManagedDraftSuggestedSkillBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    reason: str = Field(default="", max_length=512)
    available: bool = False


class WorkspaceManagedDraftPayloadBody(BaseModel):
    project: WorkspaceManagedDraftProjectBody
    workers: list[WorkspaceManagedDraftWorkerBody] = Field(default_factory=list, max_length=8)
    shared_context: str = Field(default="", max_length=16000)
    suggested_skills: list[WorkspaceManagedDraftSuggestedSkillBody] = Field(default_factory=list, max_length=16)
    questions: list[str] = Field(default_factory=list, max_length=12)


class WorkspaceManagedDraftConfirmBody(BaseModel):
    draft: WorkspaceManagedDraftPayloadBody


class WorkspaceManagedDraftFallbackPolicy(BaseModel):
    project_name_template: str = Field(..., min_length=1)
    project_description_template: str = Field(..., min_length=1)
    worker_id_template: str = Field(..., min_length=1)
    worker_display_name_template: str = Field(..., min_length=1)
    worker_role: str = Field(..., min_length=1, max_length=64)
    system_prompt_template: str = Field(..., min_length=1)
    shared_context_template: str = Field(..., min_length=1)
    model_error_note_template: str = Field(..., min_length=1)
    questions: list[str] = Field(..., max_length=12)


class WorkspaceManagedDraftConfirmPolicy(BaseModel):
    source_kind: str = Field(..., min_length=1, max_length=64)
    context_title: str = Field(..., min_length=1, max_length=160)
    change_note: str = Field(..., min_length=1, max_length=256)


class WorkspaceManagedDraftPolicy(BaseModel):
    draft_prompt_template: str = Field(..., min_length=1)
    fallback: WorkspaceManagedDraftFallbackPolicy
    confirm: WorkspaceManagedDraftConfirmPolicy


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


def _workspace_managed_draft_policy(db: Any) -> WorkspaceManagedDraftPolicy:
    content = PromptPolicyResolver(db=db).load(
        WORKSPACE_MANAGED_DRAFT_POLICY_TYPE,
        WORKSPACE_MANAGED_DRAFT_POLICY_NAME,
    )
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("managed workspace draft policy content must be valid JSON") from exc
    try:
        return WorkspaceManagedDraftPolicy.model_validate(parsed)
    except Exception as exc:
        raise RuntimeError("managed workspace draft policy is missing required templates") from exc


def _workspace_policy_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return _problem(
            503,
            "Managed workspace draft policy missing",
            "Create an active manager_task/admin_workspace_managed_draft prompt policy before using this managed flow.",
        )
    return _problem(500, "Managed workspace draft policy invalid", str(exc))


def _workspace_managed_title_seed(prompt: str) -> str:
    text = re.sub(r"\s+", " ", (prompt or "").strip())
    words = text.split()
    if not words:
        return "draft"
    title = " ".join(words[:6]).strip(" .,:;")
    return title[:1].upper() + title[1:]


def _workspace_managed_worker_id(raw: str) -> str:
    worker_id = sanitize_catalog_worker_id(raw).replace("_", "-").strip("-")
    if not worker_id:
        raise RuntimeError("managed workspace draft policy produced an empty worker_id")
    return worker_id[:64]


def _workspace_managed_template_values(
    *,
    prompt: str,
    suggested_skills: list[dict[str, Any]],
    project_name: str = "",
) -> dict[str, str]:
    goal = re.sub(r"\s+", " ", (prompt or "").strip()).strip(" .")
    title = _workspace_managed_title_seed(goal)
    slug = _workspace_managed_worker_id(title)
    values = {
        "prompt": prompt,
        "goal": goal,
        "title": title,
        "slug": slug,
        "suggested_skills_json": json.dumps(suggested_skills, ensure_ascii=False),
    }
    if project_name:
        values["project_name"] = project_name
    return values


def _workspace_managed_format(template: str, values: dict[str, str]) -> str:
    try:
        return template.format(**values).strip()
    except KeyError as exc:
        raise RuntimeError(f"managed workspace draft policy references unknown placeholder: {exc}") from exc


def _workspace_managed_fallback_draft(
    *,
    prompt: str,
    suggested_skills: list[dict[str, Any]],
    policy: WorkspaceManagedDraftPolicy,
) -> dict[str, Any]:
    values = _workspace_managed_template_values(prompt=prompt, suggested_skills=suggested_skills)
    fallback_policy = policy.fallback
    project_name = _workspace_managed_format(fallback_policy.project_name_template, values)
    values = _workspace_managed_template_values(
        prompt=prompt,
        suggested_skills=suggested_skills,
        project_name=project_name,
    )
    worker_id = _workspace_managed_worker_id(
        _workspace_managed_format(fallback_policy.worker_id_template, values)
    )
    return {
        "project": {
            "name": project_name,
            "description": _workspace_managed_format(
                fallback_policy.project_description_template,
                values,
            )[:2048],
        },
        "workers": [
            {
                "worker_id": worker_id,
                "display_name": _workspace_managed_format(
                    fallback_policy.worker_display_name_template,
                    values,
                )[:128],
                "role": _workspace_managed_format(fallback_policy.worker_role, values)[:64],
                "system_prompt": _workspace_managed_format(
                    fallback_policy.system_prompt_template,
                    values,
                )[:8000],
            }
        ],
        "shared_context": _workspace_managed_format(
            fallback_policy.shared_context_template,
            values,
        )[:16000],
        "suggested_skills": suggested_skills,
        "questions": [
            _workspace_managed_format(question, values)[:512]
            for question in fallback_policy.questions
        ],
    }


def _extract_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.I).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _workspace_managed_draft_prompt(
    prompt: str,
    suggested_skills: list[dict[str, Any]],
    policy: WorkspaceManagedDraftPolicy,
) -> str:
    return _workspace_managed_format(
        policy.draft_prompt_template,
        _workspace_managed_template_values(prompt=prompt, suggested_skills=suggested_skills),
    )


def _workspace_managed_has_configured_llm(*, tenant_id: str, actor: str) -> bool:
    llm = resolved_llm_for_playground(
        chat_id="admin-managed-workspace-draft",
        tenant_id=tenant_id,
        actor_email=actor,
    )
    return any(str(llm.get(key) or "").strip() for key in ("provider", "model", "base_url"))


def _validated_workspace_managed_draft_or_fallback(
    *,
    raw_response: str,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    parsed = _extract_json_object(raw_response)
    if not parsed:
        return fallback
    try:
        return WorkspaceManagedDraftPayloadBody.model_validate(parsed).model_dump()
    except Exception:
        return fallback


async def _workspace_managed_model_draft_or_fallback(
    *,
    actor: str,
    tenant_id: str,
    prompt: str,
    fallback: dict[str, Any],
    suggested_skills: list[dict[str, Any]],
    policy: WorkspaceManagedDraftPolicy,
) -> dict[str, Any]:
    session_id = f"admin-managed-workspace-draft-{uuid.uuid4().hex}"
    chat = ChatRequest(
        message=_workspace_managed_draft_prompt(prompt, suggested_skills, policy),
        chat_id=session_id,
        user_id=actor or "admin-ui",
        username=actor or "admin-ui",
        chat_type="private",
        tenant_id=tenant_id,
        stream=False,
    )
    try:
        # Import here to avoid a gateway main <-> admin router import cycle.
        import main as gateway_main

        result = await gateway_main._invoke_chat(
            chat,
            "default",
            session_id=session_id,
            tenant_id=tenant_id,
            redis_client=None,
            delivery_context=GatewayDeliveryContext.trusted_admin_console(),
        )
    except Exception:
        values = _workspace_managed_template_values(
            prompt=prompt,
            suggested_skills=suggested_skills,
            project_name=str(fallback.get("project", {}).get("name") or ""),
        )
        next_fallback = dict(fallback)
        next_fallback["shared_context"] = (
            f"{fallback.get('shared_context') or ''}\n\n"
            f"{_workspace_managed_format(policy.fallback.model_error_note_template, values)}"
        ).strip()
        return next_fallback
    raw = str(result.get("response") or result.get("reply") or "") if isinstance(result, dict) else str(result or "")
    return _validated_workspace_managed_draft_or_fallback(raw_response=raw, fallback=fallback)


def _workspace_managed_skill_suggestions(db: Any, *, actor_email: str, prompt: str) -> list[dict[str, Any]]:
    ensure_admin_worker_catalog_schema(db)
    profile = ensure_profile_for_user(db, email=actor_email)
    rows = db.execute(
        """
        SELECT name, description, implementation_ref
        FROM main.admin_skills
        WHERE active = true
          AND tenant_id IN (?, 'global')
          AND (owner_email = ? OR visibility = 'public')
        ORDER BY name
        """,
        [profile["tenant_id"], profile["email"]],
    )
    prompt_key = (prompt or "").lower()
    suggestions: list[dict[str, Any]] = []
    for name, description, implementation_ref in rows:
        skill_name = str(name or "").strip()
        if not skill_name:
            continue
        tokens = {part for part in re.split(r"[^a-zA-Z0-9]+", skill_name.lower()) if len(part) >= 3}
        desc = str(description or "").strip()
        matched = any(token in prompt_key for token in tokens) or (
            bool(desc) and any(part in prompt_key for part in re.split(r"[^a-zA-Z0-9]+", desc.lower()) if len(part) >= 4)
        )
        if matched:
            suggestions.append(
                {
                    "name": skill_name,
                    "reason": desc or f"Disponible como {implementation_ref}",
                    "available": True,
                }
            )
    return suggestions[:6] if suggestions else []


def _actor_profile(actor: str) -> dict[str, Any]:
    actor_email = effective_actor_email(actor)
    with open_gateway_db(read_only=True) as db:
        return ensure_profile_for_user(db, email=actor_email)


def _enqueue_workspace_managed_draft_command(command: ConfirmWorkspaceManagedDraftCommand) -> str:
    task_id = enqueue_typed_command(command, db_path=get_gateway_db_path(), user_id="default")
    command_status = poll_task_status_sync(task_id, timeout_sec=0.5)
    if command_status and command_status.status == "failed":
        raise ValueError(command_status.detail or "managed workspace draft write failed")
    return task_id


def _admin_audit(action: str, resource: str, detail: str, *, actor: str, meta: dict[str, Any] | None = None) -> None:
    # Import here because admin.py imports this domain router during startup.
    from routers import admin as admin_router

    admin_router._admin_audit(action, resource, detail, actor=actor, meta=meta)


@router.post("/workspace/orchestrator/draft", dependencies=[Depends(require_admin_key)])
async def workspace_managed_draft_compat_alias(
    body: WorkspaceManagedDraftBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    prompt = body.prompt.strip()
    tenant_id = "default"
    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=effective_actor_email(actor))
        tenant_id = str(profile.get("tenant_id") or "default").strip() or "default"
        suggested_skills = _workspace_managed_skill_suggestions(db, actor_email=effective_actor_email(actor), prompt=prompt)
        try:
            policy = _workspace_managed_draft_policy(db)
        except (FileNotFoundError, RuntimeError) as exc:
            raise _workspace_policy_error(exc) from exc
    fallback = _workspace_managed_fallback_draft(
        prompt=prompt,
        suggested_skills=suggested_skills,
        policy=policy,
    )
    if not _workspace_managed_has_configured_llm(tenant_id=tenant_id, actor=effective_actor_email(actor)):
        return fallback
    return await _workspace_managed_model_draft_or_fallback(
        actor=effective_actor_email(actor),
        tenant_id=tenant_id,
        prompt=prompt,
        fallback=fallback,
        suggested_skills=suggested_skills,
        policy=policy,
    )


@router.post("/workspace/orchestrator/confirm", dependencies=[Depends(require_admin_key)])
async def workspace_managed_draft_confirm_compat_alias(
    body: WorkspaceManagedDraftConfirmBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    draft = body.draft
    profile = _actor_profile(actor)
    actor_email = str(profile.get("email") or effective_actor_email(actor))
    tenant_id = str(profile.get("tenant_id") or "default")
    with open_gateway_db(read_only=True) as db:
        try:
            policy = _workspace_managed_draft_policy(db)
        except (FileNotFoundError, RuntimeError) as exc:
            raise _workspace_policy_error(exc) from exc
    project_id = f"prj_{uuid.uuid4().hex}"
    workers = [worker.model_dump() for worker in draft.workers]
    command = ConfirmWorkspaceManagedDraftCommand(
        project_id=project_id,
        tenant_id=tenant_id,
        actor_email=actor_email,
        project_name=draft.project.name,
        project_description=draft.project.description,
        workers=workers,
        shared_context=draft.shared_context,
        suggested_skills=[skill.model_dump() for skill in draft.suggested_skills],
        source_kind=policy.confirm.source_kind,
        context_title=policy.confirm.context_title,
        change_note=policy.confirm.change_note,
    )
    try:
        task_id = _enqueue_workspace_managed_draft_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), project_id) from exc
    project = {
        "project_id": project_id,
        "tenant_id": tenant_id,
        "owner_email": actor_email,
        "name": draft.project.name,
        "description": draft.project.description,
        "status": "active",
        "visibility": "private",
        "created_at": "",
        "updated_at": "",
    }
    created_workers = [
        {
            "worker_uid": "",
            "tenant_id": tenant_id,
            "owner_email": actor_email,
            "worker_id": worker["worker_id"],
            "display_name": worker["display_name"],
            "source_kind": policy.confirm.source_kind,
            "source_template_id": "default",
            "visibility": "private",
            "status": "active",
            "active": True,
        }
        for worker in workers
    ]
    _admin_audit(
        "workspace.managed_draft.confirm",
        project_id,
        draft.project.name,
        actor=actor_email,
        meta={"workers": [worker.get("worker_id") for worker in workers], "task_id": task_id},
    )
    return {"ok": True, "task_id": task_id, "project": project, "created": {"workers": created_workers}}
