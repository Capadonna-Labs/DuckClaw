"""LLM-assisted draft flow for admin-owned runtime agents (mirrors managed workspace draft)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from routers.admin_domains.user_agents import (
    _actor_profile,
    _enqueue_user_agent_command,
    _fallback_agent,
    _problem,
    _public_agent_from_db,
    actor_from_header,
    require_admin_key,
)
from routers.admin_domains.workspace_managed_draft import (
    _extract_json_object,
    _workspace_managed_format,
    _workspace_managed_has_configured_llm,
    _workspace_managed_skill_suggestions,
    _workspace_managed_template_values,
    _workspace_managed_worker_id,
)

from duckclaw.user_agent_draft_policy import (
    _MIN_SOUL_LEN,
    _MIN_SYSTEM_PROMPT_LEN,
    coalesce_user_agent_draft,
    sanitize_wizard_questions,
)
from duckclaw.write_commands import UpsertUserAgentCommand

router = APIRouter(tags=["admin-user-agent-draft"])

USER_AGENT_DRAFT_POLICY_TYPE = "manager_task"
USER_AGENT_DRAFT_POLICY_NAME = "admin_user_agent_draft"

_VALID_TOOL_PROFILES = frozenset({"general", "minimal", "rag_only"})


class UserAgentDraftBody(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=4000)
    display_name: str = Field(default="", max_length=128)
    worker_id: str = Field(default="", max_length=64)


class UserAgentDraftSuggestedSkillBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    reason: str = Field(default="", max_length=512)
    available: bool = False


class UserAgentDraftPayloadBody(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=128)
    worker_id: str = Field(..., min_length=1, max_length=64)
    description: str = Field(default="", max_length=2048)
    system_prompt: str = Field(default="", max_length=12000)
    soul: str = Field(default="", max_length=4000)
    tool_profile: str = Field(default="general", max_length=16)
    skills: list[str] = Field(default_factory=list, max_length=24)
    browser_sandbox: bool = False
    web_search: bool = False
    suggested_skills: list[UserAgentDraftSuggestedSkillBody] = Field(default_factory=list, max_length=16)
    questions: list[str] = Field(default_factory=list, max_length=12)


class UserAgentDraftConfirmBody(BaseModel):
    draft: UserAgentDraftPayloadBody


class UserAgentDraftFallbackPolicy(BaseModel):
    display_name_template: str = Field(..., min_length=1)
    worker_id_template: str = Field(..., min_length=1)
    description_template: str = Field(..., min_length=1)
    system_prompt_template: str = Field(..., min_length=1)
    soul_template: str = Field(..., min_length=1)
    tool_profile: str = Field(default="general", max_length=16)
    skills: list[str] = Field(default_factory=list, max_length=24)
    browser_sandbox: bool = False
    web_search: bool = False
    model_error_note_template: str = Field(..., min_length=1)
    questions: list[str] = Field(..., max_length=12)


class UserAgentDraftPolicy(BaseModel):
    draft_prompt_template: str = Field(..., min_length=1)
    fallback: UserAgentDraftFallbackPolicy


def _user_agent_draft_policy(db: Any) -> UserAgentDraftPolicy:
    from duckclaw.prompt_policies import PromptPolicyResolver

    content = PromptPolicyResolver(db=db).load(USER_AGENT_DRAFT_POLICY_TYPE, USER_AGENT_DRAFT_POLICY_NAME)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("user agent draft policy content must be valid JSON") from exc
    try:
        return UserAgentDraftPolicy.model_validate(parsed)
    except Exception as exc:
        raise RuntimeError("user agent draft policy is missing required templates") from exc


def _user_agent_policy_error(exc: Exception):
    from fastapi import HTTPException

    if isinstance(exc, FileNotFoundError):
        return _problem(
            503,
            "User agent draft policy missing",
            "Create an active manager_task/admin_user_agent_draft prompt policy before using this flow.",
        )
    return _problem(500, "User agent draft policy invalid", str(exc))


def _normalize_tool_profile(raw: str) -> str:
    del raw
    return "general"


def _user_agent_draft_prompt(
    *,
    prompt: str,
    suggested_skills: list[dict[str, Any]],
    policy: UserAgentDraftPolicy,
    display_name: str = "",
    worker_id: str = "",
) -> str:
    values = _workspace_managed_template_values(prompt=prompt, suggested_skills=suggested_skills)
    if display_name.strip():
        values["display_name_hint"] = display_name.strip()
    else:
        values["display_name_hint"] = ""
    if worker_id.strip():
        values["worker_id_hint"] = _workspace_managed_worker_id(worker_id.strip())
    else:
        values["worker_id_hint"] = ""
    return _workspace_managed_format(policy.draft_prompt_template, values)


def _user_agent_fallback_draft(
    *,
    prompt: str,
    suggested_skills: list[dict[str, Any]],
    policy: UserAgentDraftPolicy,
    display_name_hint: str = "",
    worker_id_hint: str = "",
) -> dict[str, Any]:
    values = _workspace_managed_template_values(prompt=prompt, suggested_skills=suggested_skills)
    fallback = policy.fallback
    display_name = (display_name_hint or _workspace_managed_format(fallback.display_name_template, values))[:128]
    values["display_name"] = display_name
    worker_id = worker_id_hint or _workspace_managed_worker_id(
        _workspace_managed_format(fallback.worker_id_template, values)
    )
    extra_skills = [str(s).strip() for s in fallback.skills if str(s).strip()]
    return {
        "display_name": display_name,
        "worker_id": worker_id,
        "description": _workspace_managed_format(fallback.description_template, values)[:2048],
        "system_prompt": _workspace_managed_format(fallback.system_prompt_template, values)[:12000],
        "soul": _workspace_managed_format(fallback.soul_template, values)[:4000],
        "tool_profile": _normalize_tool_profile(fallback.tool_profile),
        "skills": extra_skills,
        "browser_sandbox": bool(fallback.browser_sandbox),
        "web_search": bool(fallback.web_search),
        "suggested_skills": suggested_skills,
        "questions": sanitize_wizard_questions(
            prompt,
            [_workspace_managed_format(question, values)[:512] for question in fallback.questions],
        ),
    }


def _validated_user_agent_draft_or_fallback(
    *,
    raw_response: str,
    fallback: dict[str, Any],
    behavior_prompt: str = "",
) -> dict[str, Any]:
    parsed = _extract_json_object(raw_response)
    if not parsed:
        return fallback
    try:
        draft = UserAgentDraftPayloadBody.model_validate(parsed).model_dump()
    except Exception:
        return fallback
    merged = coalesce_user_agent_draft(
        draft,
        fallback,
        normalize_tool_profile=_normalize_tool_profile,
        behavior_prompt=behavior_prompt,
    )
    merged["questions"] = sanitize_wizard_questions(behavior_prompt, merged.get("questions") or [])
    return merged


async def _user_agent_model_draft_or_fallback(
    *,
    actor: str,
    tenant_id: str,
    prompt: str,
    fallback: dict[str, Any],
    suggested_skills: list[dict[str, Any]],
    policy: UserAgentDraftPolicy,
    display_name_hint: str = "",
    worker_id_hint: str = "",
) -> dict[str, Any]:
    session_id = f"admin-user-agent-draft-{uuid.uuid4().hex}"
    from core.models import ChatRequest
    from duckclaw.channels import GatewayDeliveryContext

    chat = ChatRequest(
        message=_user_agent_draft_prompt(
            prompt=prompt,
            suggested_skills=suggested_skills,
            policy=policy,
            display_name=display_name_hint,
            worker_id=worker_id_hint,
        ),
        chat_id=session_id,
        user_id=actor or "admin-ui",
        username=actor or "admin-ui",
        chat_type="private",
        tenant_id=tenant_id,
        stream=False,
    )

    async def _invoke():
        import main as gateway_main

        return await gateway_main._invoke_chat(
            chat,
            "default",
            session_id=session_id,
            tenant_id=tenant_id,
            redis_client=None,
            delivery_context=GatewayDeliveryContext.trusted_admin_console(),
        )

    try:
        result = await _invoke()
    except Exception:
        values = _workspace_managed_template_values(
            prompt=prompt,
            suggested_skills=suggested_skills,
            project_name=str(fallback.get("display_name") or ""),
        )
        next_fallback = dict(fallback)
        next_fallback["system_prompt"] = (
            f"{fallback.get('system_prompt') or ''}\n\n"
            f"{_workspace_managed_format(policy.fallback.model_error_note_template, values)}"
        ).strip()
        return next_fallback

    raw = str(result.get("response") or result.get("reply") or "") if isinstance(result, dict) else str(result or "")
    return _validated_user_agent_draft_or_fallback(
        raw_response=raw,
        fallback=fallback,
        behavior_prompt=prompt,
    )


def _merge_declared_skills(draft: UserAgentDraftPayloadBody) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for raw in list(draft.skills) + [skill.name for skill in draft.suggested_skills if skill.available]:
        key = str(raw or "").strip().lower().replace("-", "_")
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(key)
    if draft.web_search and "research" not in seen:
        names.append("research")
    return names


@router.post("/user-agents/draft", dependencies=[Depends(require_admin_key)])
async def create_user_agent_draft(
    body: UserAgentDraftBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import effective_actor_email, open_gateway_db

    prompt = body.prompt.strip()
    display_name_hint = body.display_name.strip()
    worker_id_hint = body.worker_id.strip()
    tenant_id = "default"
    with open_gateway_db(read_only=True) as db:
        from duckclaw.admin_user_profiles import ensure_profile_for_user

        profile = ensure_profile_for_user(db, email=effective_actor_email(actor))
        tenant_id = str(profile.get("tenant_id") or "default").strip() or "default"
        suggested_skills = _workspace_managed_skill_suggestions(
            db, actor_email=effective_actor_email(actor), prompt=prompt
        )
        try:
            policy = _user_agent_draft_policy(db)
        except (FileNotFoundError, RuntimeError) as exc:
            raise _user_agent_policy_error(exc) from exc

    fallback = _user_agent_fallback_draft(
        prompt=prompt,
        suggested_skills=suggested_skills,
        policy=policy,
        display_name_hint=display_name_hint,
        worker_id_hint=worker_id_hint,
    )
    if not _workspace_managed_has_configured_llm(tenant_id=tenant_id, actor=effective_actor_email(actor)):
        return fallback
    return await _user_agent_model_draft_or_fallback(
        actor=effective_actor_email(actor),
        tenant_id=tenant_id,
        prompt=prompt,
        fallback=fallback,
        suggested_skills=suggested_skills,
        policy=policy,
        display_name_hint=display_name_hint,
        worker_id_hint=worker_id_hint,
    )


@router.post("/user-agents/draft/confirm", dependencies=[Depends(require_admin_key)])
async def confirm_user_agent_draft(
    body: UserAgentDraftConfirmBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    draft = body.draft
    system_prompt = (draft.system_prompt or "").strip()
    soul = (draft.soul or "").strip()
    if len(system_prompt) < _MIN_SYSTEM_PROMPT_LEN:
        raise _problem(
            400,
            "Instrucciones incompletas",
            f"system_prompt debe tener al menos {_MIN_SYSTEM_PROMPT_LEN} caracteres. "
            "Regenera el borrador o edítalo en el paso de instrucciones.",
        )
    if len(soul) < _MIN_SOUL_LEN:
        raise _problem(
            400,
            "Personalidad incompleta",
            f"soul debe tener al menos {_MIN_SOUL_LEN} caracteres. "
            "Regenera el borrador o edita la personalidad antes de crear el agente.",
        )
    profile = _actor_profile(actor)
    worker_uid = f"wrk_{uuid.uuid4().hex}"
    worker_id = _workspace_managed_worker_id(draft.worker_id)
    display_name = (draft.display_name or worker_id).strip()[:128]
    skills = _merge_declared_skills(draft)
    command = UpsertUserAgentCommand(
        tenant_id=str(profile.get("tenant_id") or "default"),
        actor_email=str(profile.get("email") or actor),
        worker_uid=worker_uid,
        worker_id=worker_id,
        display_name=display_name,
        source_template_id="default",
        system_prompt=draft.system_prompt.strip(),
        description=draft.description,
        skills=skills,
        soul=soul,
        tool_profile=_normalize_tool_profile(draft.tool_profile),
        browser_sandbox=bool(draft.browser_sandbox),
        web_search=bool(draft.web_search),
    )
    try:
        task_id = _enqueue_user_agent_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), worker_id) from exc

    agent = _public_agent_from_db(str(profile.get("email") or actor), worker_id) or _fallback_agent(
        profile,
        worker_id=worker_id,
        display_name=display_name,
        source_template_id="default",
        worker_uid=worker_uid,
    )
    return {"ok": True, "task_id": task_id, "agent": agent, "worker_id": worker_id}
