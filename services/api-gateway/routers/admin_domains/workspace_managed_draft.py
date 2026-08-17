from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from core.admin_identity import effective_actor_email, open_gateway_db
from core.models import ChatRequest
from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.admin_worker_catalog import ensure_admin_worker_catalog_schema, sanitize_catalog_worker_id
from duckclaw.channels import GatewayDeliveryContext
from duckclaw.gateway_enqueue import enqueue_admin_command
from duckclaw.prompt_policies import PromptPolicyResolver
from duckclaw.spawn_package_builder import analyze_spawn_package_from_bytes
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


def _fold_ascii(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


_SKILL_SYNONYMS: dict[str, set[str]] = {
    "finance": {"finanza", "finanzas", "presupuesto", "gastos", "ingresos", "budget", "money", "dinero"},
    "budget": {"presupuesto", "gastos", "finanza", "finanzas"},
    "excel": {"hoja", "sheets", "spreadsheet", "csv", "tabla"},
    "sql": {"duckdb", "query", "consulta", "base", "datos"},
    "report": {"reporte", "informe", "dashboard"},
    "search": {"busqueda", "web", "research", "investigacion"},
}


def _prompt_tokens(prompt: str) -> set[str]:
    folded = _fold_ascii(prompt)
    tokens = {part for part in re.split(r"[^a-z0-9]+", folded) if len(part) >= 3}
    expanded = set(tokens)
    for token in tokens:
        for canonical, aliases in _SKILL_SYNONYMS.items():
            if token == canonical or token in aliases:
                expanded.add(canonical)
                expanded.update(aliases)
    return expanded


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
    prompt_tokens = _prompt_tokens(prompt)
    suggestions: list[dict[str, Any]] = []
    scored: list[tuple[int, dict[str, Any]]] = []
    for name, description, implementation_ref in rows:
        skill_name = str(name or "").strip()
        if not skill_name:
            continue
        name_tokens = {part for part in re.split(r"[^a-z0-9]+", _fold_ascii(skill_name)) if len(part) >= 3}
        desc = str(description or "").strip()
        desc_tokens = {part for part in re.split(r"[^a-z0-9]+", _fold_ascii(desc)) if len(part) >= 4}
        overlap = len(prompt_tokens & (name_tokens | desc_tokens))
        if overlap <= 0:
            continue
        scored.append(
            (
                overlap,
                {
                    "name": skill_name,
                    "reason": desc or f"Disponible como {implementation_ref}",
                    "available": True,
                },
            )
        )
    scored.sort(key=lambda item: (-item[0], item[1]["name"]))
    for _, skill in scored[:6]:
        suggestions.append(skill)
    return suggestions


def _merge_suggested_skills(
    catalog_hits: list[dict[str, Any]],
    llm_skills: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for skill in catalog_hits or []:
        name = str(skill.get("name") or "").strip()
        if not name:
            continue
        merged[name.lower()] = {
            "name": name[:128],
            "reason": str(skill.get("reason") or "")[:512],
            "available": True,
        }
    for skill in llm_skills or []:
        name = str(skill.get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        existing = merged.get(key)
        available = bool(skill.get("available")) if existing is None else True
        if existing and existing.get("available"):
            available = True
        prior_reason = str(existing.get("reason") or "") if existing else ""
        merged[key] = {
            "name": name[:128],
            "reason": str(skill.get("reason") or prior_reason)[:512],
            "available": available,
        }
    return list(merged.values())[:16]


def _actor_profile(actor: str) -> dict[str, Any]:
    actor_email = effective_actor_email(actor)
    with open_gateway_db(read_only=True) as db:
        return ensure_profile_for_user(db, email=actor_email)


def _enqueue_workspace_managed_draft_command(command: ConfirmWorkspaceManagedDraftCommand) -> str:
    return enqueue_admin_command(command)


def _admin_audit(action: str, resource: str, detail: str, *, actor: str, meta: dict[str, Any] | None = None) -> None:
    from routers import admin as admin_router

    admin_router._admin_audit(action, resource, detail, actor=actor, meta=meta)


def _runtime_tool_names() -> list[str]:
    try:
        from routers.admin_domains.worker_capabilities import build_worker_capabilities_payload

        payload = build_worker_capabilities_payload("default", actor="admin-ui")
        return [str(t).strip().lower() for t in payload.get("tools_runtime") or [] if str(t).strip()]
    except Exception:
        return ["read_sql", "inspect_schema", "get_db_path", "admin_sql"]


def _parse_spawn_import_mapping(raw: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw or "[]")
    except Exception as exc:
        raise _problem(400, "mapping_json inválido", str(exc)) from exc
    if not isinstance(parsed, list):
        raise _problem(400, "mapping_json inválido", "Se esperaba una lista")
    out: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise _problem(400, "mapping_json inválido", "Cada entrada debe ser un objeto")
        try:
            file_index = int(item.get("file_index"))
        except Exception as exc:
            raise _problem(400, "mapping_json inválido", "file_index debe ser entero") from exc
        out.append(
            {
                "file_index": file_index,
                "worker_id_override": (
                    str(item.get("worker_id_override") or "").strip()[:64] or None
                ),
                "role": str(item.get("role") or "member").strip()[:64] or "member",
                "confirm_high_risk": bool(item.get("confirm_high_risk")),
            }
        )
    return out


async def _spawn_imports_from_uploads(
    files: list[UploadFile],
    mapping: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not files:
        raise _problem(400, "Archivos requeridos", "confirm-with-import")
    if not mapping:
        raise _problem(400, "mapping_json requerido", "confirm-with-import")
    available_tools = _runtime_tool_names()
    spawn_imports: list[dict[str, Any]] = []
    for entry in mapping:
        idx = int(entry["file_index"])
        if idx < 0 or idx >= len(files):
            raise _problem(400, "file_index fuera de rango", str(idx))
        upload = files[idx]
        raw = await upload.read()
        if not raw:
            raise _problem(400, "Archivo vacío", upload.filename or str(idx))
        try:
            analysis, manifest, package_files = analyze_spawn_package_from_bytes(
                raw, available_tools=available_tools
            )
        except ValueError as exc:
            raise _problem(400, "Paquete inválido", str(exc)) from exc
        if analysis.secret_findings:
            raise _problem(
                403,
                "Secretos detectados en paquete",
                ", ".join(analysis.secret_findings[:5]),
            )
        if analysis.import_blocked_until_confirm and not entry["confirm_high_risk"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "type": "about:blank",
                    "title": "Confirmación requerida",
                    "status": 409,
                    "detail": "El paquete solicita tools de alto riesgo",
                    "high_risk_findings": analysis.high_risk_findings,
                    "file_index": idx,
                },
            )
        spawn_imports.append(
            {
                "manifest": manifest,
                "files": package_files,
                "worker_id_override": entry["worker_id_override"],
                "role": entry["role"],
                "confirm_high_risk": entry["confirm_high_risk"],
            }
        )
    return spawn_imports


def _validated_workspace_managed_draft_or_fallback(
    *,
    raw_response: str,
    fallback: dict[str, Any],
    catalog_skills: list[dict[str, Any]],
) -> dict[str, Any]:
    parsed = _extract_json_object(raw_response)
    if not parsed:
        return fallback
    try:
        draft = WorkspaceManagedDraftPayloadBody.model_validate(parsed).model_dump()
    except Exception:
        return fallback
    draft["suggested_skills"] = _merge_suggested_skills(
        catalog_skills,
        draft.get("suggested_skills") or [],
    )
    return draft


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
    return _validated_workspace_managed_draft_or_fallback(
        raw_response=raw,
        fallback=fallback,
        catalog_skills=suggested_skills,
    )


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


@router.post("/workspace/orchestrator/confirm-with-import", dependencies=[Depends(require_admin_key)])
async def workspace_managed_draft_confirm_with_import(
    draft_json: str = Form(...),
    mapping_json: str = Form(default="[]"),
    files: list[UploadFile] = File(default=[]),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    try:
        draft = WorkspaceManagedDraftPayloadBody.model_validate(json.loads(draft_json or "{}"))
    except Exception as exc:
        raise _problem(400, "draft_json inválido", str(exc)) from exc

    mapping = _parse_spawn_import_mapping(mapping_json)
    if mapping and not files:
        raise _problem(400, "Archivos requeridos", "confirm-with-import")
    spawn_imports = await _spawn_imports_from_uploads(files, mapping) if mapping else []

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
        spawn_imports=spawn_imports,
    )
    try:
        task_id = _enqueue_workspace_managed_draft_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), project_id) from exc

    imported_ids = [
        str((pkg.get("worker_id_override") or (pkg.get("manifest") or {}).get("id") or "")).strip()
        for pkg in spawn_imports
    ]
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
        "workspace.managed_draft.confirm_with_import",
        project_id,
        draft.project.name,
        actor=actor_email,
        meta={
            "workers": [worker.get("worker_id") for worker in workers],
            "spawn_imports": imported_ids,
            "task_id": task_id,
        },
    )
    return {
        "ok": True,
        "task_id": task_id,
        "project": project,
        "created": {"workers": created_workers},
        "spawn_import_count": len(spawn_imports),
    }
