"""DB-first admin routes (catalog import, workspace, user agents)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from routers.admin import _actor_from_header, _admin_audit, _problem, _require_admin_key

router = APIRouter(tags=["admin-db-first"])


class TemplateImportBody(BaseModel):
    templates_root: str = Field(..., min_length=1)
    include_prefixes: list[str] = Field(default_factory=list)
    include_template_ids: list[str] = Field(default_factory=list)


class TemplateContextBody(BaseModel):
    title: str = Field(..., min_length=1)
    content_md: str = ""
    sort_order: int = 0


class ContextReorderBody(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class WorkspaceProjectBody(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    visibility: str = "private"


class ProjectAgentBody(BaseModel):
    worker_id: str = Field(..., min_length=1)
    role: str = "member"
    sort_order: int = 0


class OrchestratorDraftBody(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=4000)


class OrchestratorDraftProjectBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(default="", max_length=2048)


class OrchestratorDraftWorkerBody(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    role: str = Field(default="member", max_length=64)
    system_prompt: str = Field(default="", max_length=8000)


class OrchestratorSuggestedSkillBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    reason: str = Field(default="", max_length=512)
    available: bool = False


class OrchestratorDraftPayloadBody(BaseModel):
    project: OrchestratorDraftProjectBody
    workers: list[OrchestratorDraftWorkerBody] = Field(default_factory=list, max_length=8)
    shared_context: str = Field(default="", max_length=16000)
    suggested_skills: list[OrchestratorSuggestedSkillBody] = Field(default_factory=list, max_length=16)
    questions: list[str] = Field(default_factory=list, max_length=12)


class OrchestratorConfirmBody(BaseModel):
    draft: OrchestratorDraftPayloadBody


class UserAgentCreateBody(BaseModel):
    worker_id: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)
    source_template_id: str = "default"
    system_prompt: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)


class RuntimeSettingPatchItem(BaseModel):
    domain: str = Field(..., min_length=1)
    key: str = Field(..., min_length=1)
    value: Any = ""
    scope: str = "actor"
    value_kind: str = "string"
    secret: bool = False


class RuntimeSettingsPatchBody(BaseModel):
    settings: list[RuntimeSettingPatchItem] = Field(default_factory=list)


class KanbanCreateBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    status: str = "pendiente"
    worker_id: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=16)
    priority: int = 0
    sort_order: int = 0


class KanbanUpdateBody(BaseModel):
    id: str = Field(..., min_length=1)
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    status: str | None = None
    worker_id: str | None = None
    tags: list[str] | None = Field(default=None, max_length=16)
    priority: int | None = None
    sort_order: int | None = None


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


class PromptPolicyUpsertBody(BaseModel):
    policy_type: str = Field(..., min_length=1, max_length=64)
    policy_name: str = Field(..., min_length=1, max_length=160)
    version: int = Field(default=1, ge=1)
    status: str = Field(default="active", max_length=32)
    content: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


_KNOWLEDGE_UPLOAD_MAX_FILES = 40
_KNOWLEDGE_UPLOAD_MAX_BYTES = 5 * 1024 * 1024


def _runtime_setting_scope(item: RuntimeSettingPatchItem, *, actor: str, tenant_id: str) -> tuple[str, str]:
    scope = (item.scope or "actor").strip().lower()
    if scope == "global":
        return "global", ""
    if scope == "tenant":
        return tenant_id, ""
    if scope == "actor":
        return tenant_id, actor
    raise ValueError(f"scope inválido: {item.scope}")


_KANBAN_UI_TO_DB_STATUS = {
    "pendiente": "todo",
    "en_progreso": "in_progress",
    "completo": "done",
    "todo": "todo",
    "in_progress": "in_progress",
    "done": "done",
    "cancelled": "cancelled",
}

_KANBAN_DB_TO_UI_STATUS = {
    "todo": "pendiente",
    "in_progress": "en_progreso",
    "done": "completo",
    "cancelled": "pendiente",
}


def _kanban_db_status(raw: str | None) -> str:
    status = str(raw or "pendiente").strip()
    mapped = _KANBAN_UI_TO_DB_STATUS.get(status)
    if not mapped:
        raise ValueError(f"status inválido: {status}")
    return mapped


def _kanban_ui_status(raw: str | None) -> str:
    return _KANBAN_DB_TO_UI_STATUS.get(str(raw or "todo").strip(), "pendiente")


def _kanban_tags(raw: Any) -> list[str]:
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw or "[]")
        except json.JSONDecodeError:
            parsed = []
    else:
        parsed = raw
    if not isinstance(parsed, list):
        return []
    out: list[str] = []
    for item in parsed:
        tag = str(item).strip()
        if tag and tag not in out:
            out.append(tag)
    return out[:16]


def _fetchone(result: Any) -> Any | None:
    if hasattr(result, "fetchone"):
        return result.fetchone()
    if isinstance(result, list):
        return result[0] if result else None
    return None


def _fetchall(result: Any) -> list[Any]:
    if hasattr(result, "fetchall"):
        return list(result.fetchall())
    if isinstance(result, list):
        return result
    return []


_PROMPT_POLICY_ALIASES = {
    "capabilities": "capability",
    "directives": "directive",
    "manager_tasks": "manager_task",
    "system_prompts": "system_prompt",
}
_PROMPT_POLICY_TYPES = {"directive", "capability", "system_prompt", "manager_task", "tool_directive"}
_PROMPT_POLICY_STATUSES = {"draft", "active", "inactive", "archived"}


def _normalize_prompt_policy_type(raw: str) -> str:
    value = str(raw or "").strip().lower()
    normalized = _PROMPT_POLICY_ALIASES.get(value, value)
    if normalized not in _PROMPT_POLICY_TYPES:
        raise ValueError(f"policy_type inválido: {raw}")
    return normalized


def _normalize_prompt_policy_status(raw: str) -> str:
    status = str(raw or "active").strip().lower()
    if status not in _PROMPT_POLICY_STATUSES:
        raise ValueError(f"status inválido: {raw}")
    return status


def _prompt_policy_id(policy_type: str, policy_name: str, version: int) -> str:
    digest = hashlib.sha256(f"{policy_type}:{policy_name}:{version}".encode("utf-8")).hexdigest()
    return f"ppol_{digest[:24]}"


def _prompt_policy_row(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        policy_id,
        policy_type,
        policy_name,
        version,
        status,
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
        "status": str(status or ""),
        "content": str(content or ""),
        "checksum": str(checksum or ""),
        "metadata": metadata if isinstance(metadata, dict) else {},
        "active": bool(active),
        "created_at": str(created_at),
        "updated_at": str(updated_at),
    }


def _kanban_card_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    card_id, title, description, status, worker_id, tags_json, created_at, updated_at = row
    return {
        "id": str(card_id),
        "title": str(title or ""),
        "description": str(description or ""),
        "status": _kanban_ui_status(str(status or "todo")),
        "worker_id": str(worker_id or "") or None,
        "tags": _kanban_tags(tags_json),
        "created_at": str(created_at),
        "updated_at": str(updated_at),
    }


def _kanban_existing_card(db: Any, *, card_id: str, tenant_id: str, actor_email: str) -> dict[str, Any] | None:
    row = _fetchone(
        db.execute(
            "SELECT card_id, title, description, status, assignee_email, tags_json, created_at, updated_at "
            "FROM main.admin_kanban_cards "
            "WHERE card_id = ? AND tenant_id = ? AND actor_email = ?",
            [card_id, tenant_id, actor_email],
        )
    )
    return _kanban_card_from_row(row) if row else None


def _enqueue_kanban_command(command: Any) -> str:
    from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync
    from duckclaw.gateway_db import get_gateway_db_path

    task_id = enqueue_typed_command(command, db_path=get_gateway_db_path(), user_id="default")
    status = poll_task_status_sync(task_id, timeout_sec=0.5)
    if status and status.status == "failed":
        raise ValueError(status.detail or "kanban write failed")
    return task_id


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


def _enqueue_prompt_policy_command(command: Any) -> str:
    from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync
    from duckclaw.gateway_db import get_gateway_db_path

    task_id = enqueue_typed_command(command, db_path=get_gateway_db_path(), user_id="default")
    status = poll_task_status_sync(task_id, timeout_sec=0.5)
    if status and status.status == "failed":
        detail = status.detail or "prompt policy write failed"
        if "No hay query SQL" in detail:
            raise ValueError(
                "DB-Writer desactualizado: reinicia DuckClaw-DB-Writer y DuckClaw-Gateway para aplicar comandos de prompt policies."
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


def _knowledge_source_row(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        source_id,
        tenant_id,
        project_id,
        worker_uid,
        source_kind,
        source_uri,
        display_name,
        status,
        metadata_json,
        active,
        created_at,
        updated_at,
        document_count,
        chunk_count,
    ) = row
    try:
        metadata = json.loads(metadata_json or "{}")
    except json.JSONDecodeError:
        metadata = {}
    return {
        "source_id": str(source_id),
        "tenant_id": str(tenant_id or ""),
        "project_id": str(project_id or ""),
        "worker_uid": str(worker_uid or ""),
        "source_kind": str(source_kind or ""),
        "source_uri": str(source_uri or ""),
        "display_name": str(display_name or ""),
        "status": str(status or ""),
        "metadata": metadata,
        "active": bool(active),
        "created_at": str(created_at),
        "updated_at": str(updated_at),
        "document_count": int(document_count or 0),
        "chunk_count": int(chunk_count or 0),
    }


def _orchestrator_title_from_prompt(prompt: str) -> str:
    text = re.sub(r"\s+", " ", (prompt or "").strip())
    cleaned = re.sub(r"^(crear|crea|necesito|quiero|ayudame a crear)\s+", "", text, flags=re.I)
    words = cleaned.split()
    if not words:
        return "Proyecto guiado"
    title = " ".join(words[:6]).strip(" .,:;")
    return title[:1].upper() + title[1:]


def _orchestrator_worker_id_from_project(name: str) -> str:
    from duckclaw.admin_worker_catalog import sanitize_catalog_worker_id

    base = sanitize_catalog_worker_id(name or "guided-agent").replace("_", "-")
    if not base.endswith("-agent"):
        base = f"{base}-agent"
    return base[:64] or "guided-agent"


def _orchestrator_description_from_prompt(prompt: str, project_name: str) -> str:
    goal = re.sub(r"\s+", " ", (prompt or "").strip()).strip(" .")
    if not goal:
        return f"Proyecto orientado a estructurar {project_name} con guía del Platform Orchestrator."
    if len(goal) > 220:
        goal = goal[:217].rstrip() + "..."
    return (
        f"Proyecto orientado a convertir el objetivo '{goal}' en un flujo DB-first con contexto, "
        "workers sugeridos y pasos de validación antes de ejecutar cambios."
    )[:512]


def _orchestrator_worker_display_name(project_name: str) -> str:
    base = re.sub(r"\s+", " ", (project_name or "Proyecto guiado").strip())
    return f"Asistente {base}"[:128]


def _orchestrator_fallback_draft(
    *,
    prompt: str,
    suggested_skills: list[dict[str, Any]],
) -> dict[str, Any]:
    project_name = _orchestrator_title_from_prompt(prompt)
    worker_id = _orchestrator_worker_id_from_project(project_name)
    project_description = _orchestrator_description_from_prompt(prompt, project_name)
    shared_context = "\n".join(
        [
            "# Análisis del Orchestrator",
            "",
            "## Lectura del objetivo",
            prompt,
            "",
            "## Supuestos iniciales",
            "- El proyecto debe operar con configuración DB-first.",
            "- El usuario revisará el borrador antes de persistir cambios.",
            "- Los workers sugeridos deben pedir datos faltantes antes de actuar.",
        ]
    )
    return {
        "project": {
            "name": project_name,
            "description": project_description,
        },
        "workers": [
            {
                "worker_id": worker_id,
                "display_name": _orchestrator_worker_display_name(project_name),
                "role": "member",
                "system_prompt": (
                    f"Actúa como asistente especializado del proyecto {project_name}. "
                    "Usa el contexto compartido, convierte objetivos en pasos verificables y pregunta antes "
                    "de asumir datos faltantes."
                ),
            }
        ],
        "shared_context": shared_context,
        "suggested_skills": suggested_skills,
        "questions": [
            "¿Qué fuentes de datos debe usar este proyecto?",
            "¿Qué resultado concreto esperas del worker principal?",
            "¿Hay restricciones de tono, seguridad o aprobación humana?",
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


def _orchestrator_draft_prompt(prompt: str, suggested_skills: list[dict[str, Any]]) -> str:
    return (
        "Actúas como Platform Orchestrator de DuckClaw.\n"
        "Responde SOLO JSON válido, sin markdown, sin texto extra.\n"
        "No inventes secretos. No escribas en DB. Solo prepara un borrador revisable.\n"
        "Schema exacto:\n"
        "{"
        '"project":{"name":"string","description":"string"},'
        '"workers":[{"worker_id":"string","display_name":"string","role":"member","system_prompt":"string"}],'
        '"shared_context":"markdown string",'
        '"suggested_skills":[{"name":"string","reason":"string","available":true}],'
        '"questions":["string"]'
        "}\n"
        f"Skills detectadas o sugeridas: {json.dumps(suggested_skills, ensure_ascii=False)}\n"
        f"Objetivo del usuario:\n{prompt}"
    )


def _orchestrator_has_configured_llm(*, tenant_id: str, actor: str) -> bool:
    from routers.admin import _resolved_llm_for_playground

    llm = _resolved_llm_for_playground(
        chat_id="admin-orchestrator-draft",
        tenant_id=tenant_id,
        actor_email=actor,
    )
    return any(str(llm.get(key) or "").strip() for key in ("provider", "model", "base_url"))


def _validated_orchestrator_draft_or_fallback(
    *,
    raw_response: str,
    fallback: dict[str, Any],
) -> dict[str, Any]:
    parsed = _extract_json_object(raw_response)
    if not parsed:
        return fallback
    try:
        return OrchestratorDraftPayloadBody.model_validate(parsed).model_dump()
    except Exception:
        return fallback


async def _orchestrator_model_draft_or_fallback(
    *,
    actor: str,
    tenant_id: str,
    prompt: str,
    fallback: dict[str, Any],
    suggested_skills: list[dict[str, Any]],
) -> dict[str, Any]:
    from core.models import ChatRequest
    from duckclaw.channels import GatewayDeliveryContext
    import main as gateway_main

    session_id = f"admin-orchestrator-draft-{uuid.uuid4().hex}"
    chat = ChatRequest(
        message=_orchestrator_draft_prompt(prompt, suggested_skills),
        chat_id=session_id,
        user_id=actor or "admin-ui",
        username=actor or "admin-ui",
        chat_type="private",
        tenant_id=tenant_id,
        stream=False,
    )
    try:
        result = await gateway_main._invoke_chat(
            chat,
            "platform-orchestrator",
            session_id=session_id,
            tenant_id=tenant_id,
            redis_client=None,
            delivery_context=GatewayDeliveryContext.trusted_admin_console(),
        )
    except Exception:
        next_fallback = dict(fallback)
        next_fallback["shared_context"] = (
            f"{fallback.get('shared_context') or ''}\n\n"
            "> Nota: no se pudo invocar el modelo configurado; se usó análisis local estructurado."
        ).strip()
        return next_fallback
    raw = ""
    if isinstance(result, dict):
        raw = str(result.get("response") or result.get("reply") or "")
    else:
        raw = str(result or "")
    return _validated_orchestrator_draft_or_fallback(raw_response=raw, fallback=fallback)


def _orchestrator_skill_suggestions(db: Any, *, actor_email: str, prompt: str) -> list[dict[str, Any]]:
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.admin_worker_catalog import ensure_admin_worker_catalog_schema

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
    if suggestions:
        return suggestions[:6]
    return []


@router.post("/templates/import", dependencies=[Depends(_require_admin_key)])
async def import_templates_to_catalog(
    body: TemplateImportBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_template_import import import_templates_to_catalog as _import

    with open_gateway_db(read_only=False) as db:
        return _import(
            db,
            owner_email=actor,
            templates_root=body.templates_root,
            include_prefixes=tuple(body.include_prefixes),
            include_template_ids=tuple(body.include_template_ids),
        )


@router.post("/templates/{worker_id}/contexts", dependencies=[Depends(_require_admin_key)])
async def create_template_context(
    worker_id: str,
    body: TemplateContextBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_worker_catalog import add_catalog_worker_context, get_visible_worker_for_actor

    with open_gateway_db(read_only=False) as db:
        worker = get_visible_worker_for_actor(db, actor_email=actor, worker_id=worker_id)
        if not worker:
            raise _problem(404, "Worker no visible en catálogo", worker_id)
        return add_catalog_worker_context(
            db,
            worker_uid=worker["worker_uid"],
            title=body.title,
            content_md=body.content_md,
            sort_order=body.sort_order,
            actor_email=actor,
        )


@router.patch("/templates/{worker_id}/contexts/reorder", dependencies=[Depends(_require_admin_key)])
async def reorder_template_contexts(
    worker_id: str,
    body: ContextReorderBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_worker_catalog import get_visible_worker_for_actor, reorder_worker_contexts

    with open_gateway_db(read_only=False) as db:
        worker = get_visible_worker_for_actor(db, actor_email=actor, worker_id=worker_id)
        if not worker:
            raise _problem(404, "Worker no visible en catálogo", worker_id)
        updated = reorder_worker_contexts(db, worker_uid=worker["worker_uid"], items=body.items)
    return {"updated": updated}


@router.delete("/templates/{worker_id}/contexts/{context_id}", dependencies=[Depends(_require_admin_key)])
async def delete_template_context(
    worker_id: str,
    context_id: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_worker_catalog import deactivate_worker_context, get_visible_worker_for_actor

    with open_gateway_db(read_only=False) as db:
        worker = get_visible_worker_for_actor(db, actor_email=actor, worker_id=worker_id)
        if not worker:
            raise _problem(404, "Worker no visible en catálogo", worker_id)
        result = deactivate_worker_context(
            db,
            worker_uid=worker["worker_uid"],
            context_id=context_id,
            actor_email=actor,
        )
        if not result:
            raise _problem(404, "Contexto no encontrado", context_id)
    return {"ok": True, **result}


@router.get("/settings/runtime", dependencies=[Depends(_require_admin_key)])
async def list_runtime_settings(
    domain: list[str] | None = Query(None),
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_runtime_settings import list_runtime_settings_effective
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    with open_gateway_db(read_only=False) as db:
        profile = ensure_profile_for_user(db, email=actor)
        settings = list_runtime_settings_effective(
            db,
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            domains=domain or None,
        )
    return {
        "tenant_id": profile["tenant_id"],
        "actor_email": profile["email"],
        "settings": settings,
    }


@router.patch("/settings/runtime", dependencies=[Depends(_require_admin_key)])
async def patch_runtime_settings(
    body: RuntimeSettingsPatchBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_resources import record_resource_event
    from duckclaw.admin_runtime_settings import upsert_runtime_setting
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    updated: list[str] = []
    with open_gateway_db(read_only=False) as db:
        profile = ensure_profile_for_user(db, email=actor)
        for item in body.settings:
            tenant_id, scoped_actor = _runtime_setting_scope(
                item,
                actor=profile["email"],
                tenant_id=profile["tenant_id"],
            )
            value = item.value
            value_json = value if isinstance(value, (dict, list)) else None
            value_text = "" if value_json is not None else str(value or "")
            upsert_runtime_setting(
                db,
                tenant_id=tenant_id,
                actor_email=scoped_actor,
                domain=item.domain,
                key=item.key,
                value_text=value_text,
                value_json=value_json,
                value_kind="json" if value_json is not None else item.value_kind,
                secret=item.secret,
                updated_by=profile["email"],
            )
            domain_key = f"{item.domain.strip().lower()}.{item.key.strip().lower()}"
            updated.append(domain_key)
            record_resource_event(
                db,
                tenant_id=profile["tenant_id"],
                actor_email=profile["email"],
                resource_kind="runtime_setting",
                resource_id=domain_key,
                event_type="runtime_setting.updated",
                payload={"domain": item.domain, "setting": item.key, "scope": item.scope},
            )
    return {"ok": True, "updated": updated}


@router.get("/prompt-policies", dependencies=[Depends(_require_admin_key)])
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


@router.put("/prompt-policies", dependencies=[Depends(_require_admin_key)])
async def upsert_prompt_policy(
    body: PromptPolicyUpsertBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from duckclaw.write_commands import UpsertPromptPolicyCommand

    try:
        policy_type = _normalize_prompt_policy_type(body.policy_type)
        status = _normalize_prompt_policy_status(body.status)
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
            status=status,  # type: ignore[arg-type]
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
            "status": status,
            "active": status == "active",
        },
    }


@router.delete("/prompt-policies/{policy_type}/{policy_name}", dependencies=[Depends(_require_admin_key)])
async def deactivate_prompt_policy(
    policy_type: str,
    policy_name: str,
    version: int | None = Query(None, ge=1),
    actor: str = Depends(_actor_from_header),
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


@router.get("/kanban", dependencies=[Depends(_require_admin_key)])
async def list_kanban_cards(
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    with open_gateway_db(read_only=False) as db:
        profile = ensure_profile_for_user(db, email=actor)
        rows = _fetchall(
            db.execute(
                "SELECT card_id, title, description, status, assignee_email, tags_json, created_at, updated_at "
                "FROM main.admin_kanban_cards "
                "WHERE tenant_id = ? AND actor_email = ? AND status <> 'cancelled' "
                "ORDER BY sort_order ASC, updated_at DESC",
                [profile["tenant_id"], profile["email"]],
            )
        )
    return {"cards": [_kanban_card_from_row(row) for row in rows]}


@router.post("/kanban", dependencies=[Depends(_require_admin_key)])
async def create_kanban_card(
    body: KanbanCreateBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.write_commands import UpsertKanbanCardCommand

    with open_gateway_db(read_only=False) as db:
        profile = ensure_profile_for_user(db, email=actor)

    try:
        status = _kanban_db_status(body.status)
        command = UpsertKanbanCardCommand(
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            title=body.title.strip(),
            description=body.description.strip(),
            status=status,  # type: ignore[arg-type]
            priority=body.priority,
            sort_order=body.sort_order,
            worker_id=(body.worker_id or "").strip(),
            tags=body.tags,
        )
        task_id = _enqueue_kanban_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), "kanban") from exc

    card = {
        "id": command.card_id,
        "title": command.title,
        "description": command.description,
        "status": _kanban_ui_status(command.status),
        "worker_id": command.worker_id or None,
        "tags": command.tags,
        "created_at": "",
        "updated_at": "",
    }
    return {"ok": True, "task_id": task_id, "card": card}


@router.patch("/kanban", dependencies=[Depends(_require_admin_key)])
async def update_kanban_card(
    body: KanbanUpdateBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.write_commands import UpsertKanbanCardCommand

    with open_gateway_db(read_only=False) as db:
        profile = ensure_profile_for_user(db, email=actor)
        existing = _kanban_existing_card(
            db,
            card_id=body.id,
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
        )
    if not existing:
        raise _problem(404, "Tarjeta no encontrada", body.id)

    try:
        status = _kanban_db_status(body.status or existing["status"])
        tags = body.tags if body.tags is not None else existing["tags"]
        command = UpsertKanbanCardCommand(
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            card_id=body.id,
            title=(body.title if body.title is not None else existing["title"]).strip(),
            description=(body.description if body.description is not None else existing["description"]).strip(),
            status=status,  # type: ignore[arg-type]
            priority=body.priority if body.priority is not None else 0,
            sort_order=body.sort_order if body.sort_order is not None else 0,
            worker_id=((body.worker_id if body.worker_id is not None else existing.get("worker_id")) or "").strip(),
            tags=tags,
        )
        task_id = _enqueue_kanban_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), body.id) from exc

    card = {
        "id": command.card_id,
        "title": command.title,
        "description": command.description,
        "status": _kanban_ui_status(command.status),
        "worker_id": command.worker_id or None,
        "tags": command.tags,
        "created_at": existing["created_at"],
        "updated_at": "",
    }
    return {"ok": True, "task_id": task_id, "card": card}


@router.delete("/kanban", dependencies=[Depends(_require_admin_key)])
async def delete_kanban_card(
    id: str = Query(..., min_length=1),
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.write_commands import DeleteKanbanCardCommand

    with open_gateway_db(read_only=False) as db:
        profile = ensure_profile_for_user(db, email=actor)

    try:
        command = DeleteKanbanCardCommand(
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            card_id=id,
        )
        task_id = _enqueue_kanban_command(command)
    except ValueError as exc:
        raise _problem(404, str(exc), id) from exc
    return {"ok": True, "task_id": task_id}


@router.get("/knowledge/sources", dependencies=[Depends(_require_admin_key)])
async def list_knowledge_sources(
    project_id: str = "",
    worker_uid: str = "",
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)
        clauses = ["s.tenant_id = ?", "s.active = true"]
        params: list[Any] = [profile["tenant_id"]]
        if project_id:
            clauses.append("(s.project_id = ? OR s.project_id = '')")
            params.append(project_id)
        if worker_uid:
            clauses.append("(s.worker_uid = ? OR s.worker_uid = '')")
            params.append(worker_uid)
        rows = _fetchall(
            db.execute(
                f"""
                SELECT s.source_id, s.tenant_id, s.project_id, s.worker_uid, s.source_kind,
                       s.source_uri, s.display_name, s.status, s.metadata_json, s.active,
                       s.created_at, s.updated_at,
                       COUNT(DISTINCT d.document_id) AS document_count,
                       COUNT(DISTINCT c.chunk_id) AS chunk_count
                FROM main.admin_knowledge_sources s
                LEFT JOIN main.admin_knowledge_documents d
                  ON d.source_id = s.source_id AND d.active = true
                LEFT JOIN main.admin_knowledge_chunks c
                  ON c.source_id = s.source_id
                 AND c.active = true
                 AND (s.project_id = '' OR c.project_id = s.project_id OR c.project_id = '')
                 AND (s.worker_uid = '' OR c.worker_uid = s.worker_uid OR c.worker_uid = '')
                WHERE {' AND '.join(clauses)}
                GROUP BY s.source_id, s.tenant_id, s.project_id, s.worker_uid, s.source_kind,
                         s.source_uri, s.display_name, s.status, s.metadata_json, s.active,
                         s.created_at, s.updated_at
                ORDER BY s.updated_at DESC
                """,
                params,
            )
        )
    return {"sources": [_knowledge_source_row(row) for row in rows]}


@router.post("/knowledge/sources", dependencies=[Depends(_require_admin_key)])
async def create_knowledge_source(
    body: KnowledgeSourceCreateBody,
    actor: str = Depends(_actor_from_header),
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
        raise _problem(400, str(exc), "knowledge_source") from exc

    return {
        "ok": True,
        "source_id": source_id,
        "task_ids": task_ids,
        "documents": documents,
        "chunks": chunks,
    }


@router.post("/knowledge/uploads", dependencies=[Depends(_require_admin_key)])
async def upload_knowledge_files(
    project_id: str = Form(default=""),
    worker_uid: str = Form(default=""),
    display_name: str = Form(default=""),
    compute_embeddings: bool = Form(default=False),
    files: list[UploadFile] = File(...),
    actor: str = Depends(_actor_from_header),
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
        raise _problem(400, "Debes subir al menos un archivo", "knowledge_upload")
    if len(files) > _KNOWLEDGE_UPLOAD_MAX_FILES:
        raise _problem(400, f"Máximo {_KNOWLEDGE_UPLOAD_MAX_FILES} archivos por carga", "knowledge_upload")

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
        raise _problem(400, "No se pudo procesar la carga RAG", str(exc)) from exc

    return {
        "ok": True,
        "source_id": source_id,
        "task_ids": task_ids,
        "documents": documents,
        "chunks": chunks,
    }


@router.delete("/knowledge/sources/{source_id}", dependencies=[Depends(_require_admin_key)])
async def deactivate_knowledge_source(
    source_id: str,
    actor: str = Depends(_actor_from_header),
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
        raise _problem(404, str(exc), source_id) from exc
    return {"ok": True, "source_id": source_id, "task_id": task_id}


@router.post("/knowledge/search", dependencies=[Depends(_require_admin_key)])
async def search_knowledge(
    body: KnowledgeSearchBody,
    actor: str = Depends(_actor_from_header),
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


@router.get("/workspace/projects", dependencies=[Depends(_require_admin_key)])
async def list_workspace_projects(
    q: str = "",
    status: str = "active",
    sort: str = "updated_at",
    direction: str = "desc",
    limit: int = 25,
    offset: int = 0,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import list_workspace_projects_page_for_actor, open_gateway_db

    with open_gateway_db(read_only=True) as db:
        return list_workspace_projects_page_for_actor(
            db,
            actor_email=actor,
            q=q,
            status=status,
            sort=sort,
            direction=direction,
            limit=limit,
            offset=offset,
        )


@router.post("/workspace/projects", dependencies=[Depends(_require_admin_key)])
async def create_workspace_project(
    body: WorkspaceProjectBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import create_project, open_gateway_db

    with open_gateway_db(read_only=False) as db:
        project = create_project(
            db,
            owner_email=actor,
            name=body.name,
            description=body.description,
            visibility=body.visibility,
        )
    return {"project": project}


@router.get("/workspace/projects/{project_id}", dependencies=[Depends(_require_admin_key)])
async def get_workspace_project(
    project_id: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db, project_context_for_actor

    with open_gateway_db(read_only=True) as db:
        project = project_context_for_actor(db, actor_email=actor, project_id=project_id)
    if not project:
        raise _problem(404, "Proyecto no encontrado o no pertenece al actor", project_id)
    agents = list(project.get("agents") or [])
    return {"project": project, "agents": agents}


@router.delete("/workspace/projects/{project_id}", dependencies=[Depends(_require_admin_key)])
async def delete_workspace_project(
    project_id: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import deactivate_workspace_project_for_actor, open_gateway_db

    with open_gateway_db(read_only=False) as db:
        db.execute("BEGIN TRANSACTION")
        try:
            ok = deactivate_workspace_project_for_actor(db, actor_email=actor, project_id=project_id)
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    if not ok:
        raise _problem(404, "Proyecto no encontrado o no pertenece al actor", project_id)
    return {"ok": True, "hard_deleted": True, "project_id": project_id}


@router.post("/workspace/projects/{project_id}/deactivate", dependencies=[Depends(_require_admin_key)])
async def deactivate_workspace_project(
    project_id: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db, set_workspace_project_status_for_actor

    with open_gateway_db(read_only=False) as db:
        project = set_workspace_project_status_for_actor(
            db,
            actor_email=actor,
            project_id=project_id,
            status="inactive",
        )
    if project is None:
        raise _problem(404, "Proyecto no encontrado o no pertenece al actor", project_id)
    return {"ok": True, "project": project}


@router.post("/workspace/projects/{project_id}/reactivate", dependencies=[Depends(_require_admin_key)])
async def reactivate_workspace_project(
    project_id: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db, set_workspace_project_status_for_actor

    with open_gateway_db(read_only=False) as db:
        project = set_workspace_project_status_for_actor(
            db,
            actor_email=actor,
            project_id=project_id,
            status="active",
        )
    if project is None:
        raise _problem(404, "Proyecto no encontrado o no pertenece al actor", project_id)
    return {"ok": True, "project": project}


@router.get("/workspace/projects/{project_id}/agents", dependencies=[Depends(_require_admin_key)])
async def list_workspace_project_agents(
    project_id: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import list_project_agents, open_gateway_db

    with open_gateway_db(read_only=True) as db:
        agents = list_project_agents(db, project_id=project_id, actor_email=actor)
    return {"agents": agents}


@router.post("/workspace/projects/{project_id}/agents", dependencies=[Depends(_require_admin_key)])
async def attach_workspace_project_agent(
    project_id: str,
    body: ProjectAgentBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import attach_project_agent_by_worker_id, open_gateway_db

    try:
        with open_gateway_db(read_only=False) as db:
            return attach_project_agent_by_worker_id(
                db,
                actor_email=actor,
                project_id=project_id,
                worker_id=body.worker_id,
                role=body.role,
                sort_order=body.sort_order,
            )
    except ValueError as exc:
        raise _problem(400, str(exc), body.worker_id) from exc


@router.delete(
    "/workspace/projects/{project_id}/agents/{worker_id}",
    dependencies=[Depends(_require_admin_key)],
)
async def detach_workspace_project_agent(
    project_id: str,
    worker_id: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import detach_project_agent_by_worker_id, open_gateway_db

    with open_gateway_db(read_only=False) as db:
        ok = detach_project_agent_by_worker_id(
            db,
            actor_email=actor,
            project_id=project_id,
            worker_id=worker_id,
        )
    return {"ok": ok}


@router.post("/workspace/orchestrator/draft", dependencies=[Depends(_require_admin_key)])
async def workspace_orchestrator_draft(
    body: OrchestratorDraftBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_worker_catalog import ensure_platform_orchestrator_for_actor

    prompt = body.prompt.strip()
    tenant_id = "default"
    with open_gateway_db(read_only=False) as db:
        orchestrator = ensure_platform_orchestrator_for_actor(db, actor_email=actor)
        tenant_id = str(orchestrator.get("tenant_id") or "default").strip() or "default"
        suggested_skills = _orchestrator_skill_suggestions(db, actor_email=actor, prompt=prompt)
    fallback = _orchestrator_fallback_draft(prompt=prompt, suggested_skills=suggested_skills)
    if not _orchestrator_has_configured_llm(tenant_id=tenant_id, actor=actor):
        return fallback
    return await _orchestrator_model_draft_or_fallback(
        actor=actor,
        tenant_id=tenant_id,
        prompt=prompt,
        fallback=fallback,
        suggested_skills=suggested_skills,
    )


@router.post("/workspace/orchestrator/confirm", dependencies=[Depends(_require_admin_key)])
async def workspace_orchestrator_confirm(
    body: OrchestratorConfirmBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_worker_catalog import (
        add_worker_context,
        add_worker_version,
        create_worker,
        ensure_platform_orchestrator_for_actor,
        get_visible_worker_for_actor,
    )
    from duckclaw.admin_workspace import (
        attach_agent_to_project,
        create_project as create_workspace_project,
        ensure_admin_workspace_schema,
    )

    draft = body.draft
    created_workers: list[dict[str, Any]] = []
    with open_gateway_db(read_only=False) as db:
        ensure_platform_orchestrator_for_actor(db, actor_email=actor)
        ensure_admin_workspace_schema(db)
        db.execute("BEGIN TRANSACTION")
        try:
            project = create_workspace_project(
                db,
                owner_email=actor,
                name=draft.project.name,
                description=draft.project.description,
            )
            for index, worker_body in enumerate(draft.workers):
                existing = get_visible_worker_for_actor(
                    db,
                    actor_email=actor,
                    worker_id=worker_body.worker_id,
                )
                worker = existing or create_worker(
                    db,
                    owner_email=actor,
                    worker_id=worker_body.worker_id,
                    display_name=worker_body.display_name,
                    source_kind="orchestrator_draft",
                    source_template_id="platform-orchestrator",
                    visibility="private",
                )
                if existing is None:
                    add_worker_version(
                        db,
                        worker_uid=worker["worker_uid"],
                        created_by=actor,
                        manifest_snapshot={
                            "id": worker["worker_id"],
                            "name": worker["display_name"],
                            "description": draft.project.description,
                            "skills": [skill.name for skill in draft.suggested_skills if skill.available],
                        },
                        files_snapshot={
                            "system_prompt.md": worker_body.system_prompt,
                            "soul.md": draft.shared_context,
                        },
                        change_note="Creado desde Platform Orchestrator",
                    )
                if draft.shared_context.strip():
                    add_worker_context(
                        db,
                        worker_uid=worker["worker_uid"],
                        title="Contexto compartido",
                        content_md=draft.shared_context,
                        sort_order=0,
                    )
                attach_agent_to_project(
                    db,
                    project_id=project["project_id"],
                    worker_uid=worker["worker_uid"],
                    role=worker_body.role or "member",
                    sort_order=index,
                )
                created_workers.append(worker)
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    _admin_audit(
        "workspace.orchestrator.confirm",
        str(project.get("project_id")),
        str(project.get("name")),
        actor=actor,
        meta={"workers": [worker.get("worker_id") for worker in created_workers]},
    )
    return {"ok": True, "project": project, "created": {"workers": created_workers}}


@router.post("/user-agents", dependencies=[Depends(_require_admin_key)])
async def create_user_agent(
    body: UserAgentCreateBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_agents import create_runtime_agent

    try:
        with open_gateway_db(read_only=False) as db:
            agent = create_runtime_agent(
                db,
                owner_email=actor,
                worker_id=body.worker_id,
                display_name=body.display_name,
                source_template_id=body.source_template_id,
                system_prompt=body.system_prompt,
                description=body.description,
                skills=body.skills,
            )
    except ValueError as exc:
        raise _problem(400, str(exc), body.worker_id) from exc
    return {"agent": agent}
