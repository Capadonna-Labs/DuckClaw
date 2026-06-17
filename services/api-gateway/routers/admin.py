from __future__ import annotations

import logging
import os
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

from routers.admin_domains.access_management import router as access_management_router
from routers.admin_domains.admin_common import (
    actor_from_header as _actor_from_header,
    admin_audit as _admin_audit,
    audit_log_path as _audit_log_path,
    mask_secret as _mask_secret,
    problem as _problem,
    repo_root as _repo_root,
    require_admin_key as _require_admin_key,
)
from routers.admin_domains.audit import router as audit_router
from routers.admin_domains.auth import router as auth_router
from routers.admin_domains.catalog_meta import router as catalog_meta_router
from routers.admin_domains.catalog_skills import router as catalog_skills_router
from routers.admin_domains.duckdb_explorer import router as duckdb_explorer_router
from routers.admin_domains.env_config import env_file as _env_file
from routers.admin_domains.env_config import router as env_config_router
from routers.admin_domains.fly_commands_catalog import router as fly_commands_catalog_router
from routers.admin_domains.forge_projects import router as forge_projects_router
from routers.admin_domains.hitl_admin import router as hitl_admin_router
from routers.admin_domains.kanban import router as kanban_router
from routers.admin_domains.kanban_runtime import router as kanban_runtime_router
from routers.admin_domains.ops import router as ops_router
from routers.admin_domains.overview import gateway_db_query_rows as _gateway_db_query_rows
from routers.admin_domains.overview import overview_usage_metrics as _overview_usage_metrics
from routers.admin_domains.overview import router as overview_router
from routers.admin_domains.playground_chat import (
    _open_playground_vault_db,
    _pick_playground_worker,
    _playground_team_context,
    _playground_telegram_user_id,
    _playground_vault_db_path,
)
from routers.admin_domains.playground_chat import router as playground_chat_router
from routers.admin_domains.prompt_policies import router as prompt_policies_router
from routers.admin_domains.runtime_config import router as runtime_config_router
from routers.admin_domains.sandbox_sessions import router as sandbox_sessions_router
from routers.admin_domains.telegram_routes import router as telegram_routes_router
from routers.admin_domains.template_contexts import router as template_contexts_router
from routers.admin_domains.templates_catalog import router as templates_catalog_router
from routers.admin_domains.template_lifecycle import (
    FileWriteBody,
    TemplateCreateBody,
    VaultBindingPutBody,
    create_template_impl as _create_template_impl,
    create_worker_from_source as _create_worker_from_source,
    delete_template_impl as _delete_template_impl,
    get_template_impl as _get_template_impl,
    get_template_vault_binding_impl as _get_template_vault_binding_impl,
    hard_delete_template_impl as _hard_delete_template_impl,
    list_template_files as _list_template_files,
    list_templates_impl as _list_templates_impl,
    put_template_file_impl as _put_template_file_impl,
    put_template_vault_binding_impl as _put_template_vault_binding_impl,
    reactivate_template_impl as _reactivate_template_impl,
    safe_worker_path as _safe_worker_path,
    template_card_description as _template_card_description,
    template_vault_options_impl as _template_vault_options_impl,
    templates_dir as _templates_dir,
    validate_template_impl as _validate_template_impl,
)
from routers.admin_domains.user_agents import router as user_agents_router
from routers.admin_domains.visual_assets import router as visual_assets_router
from routers.admin_domains.workspace_managed_draft import router as workspace_managed_draft_router
from routers.admin_domains.workspace_projects import router as workspace_projects_router

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
router.include_router(access_management_router)
router.include_router(audit_router)
router.include_router(auth_router)
router.include_router(catalog_meta_router)
router.include_router(catalog_skills_router)
router.include_router(duckdb_explorer_router)
router.include_router(env_config_router)
router.include_router(fly_commands_catalog_router)
router.include_router(forge_projects_router)
router.include_router(hitl_admin_router)
router.include_router(kanban_router)
router.include_router(kanban_runtime_router)
router.include_router(ops_router)
router.include_router(overview_router)
router.include_router(playground_chat_router)
router.include_router(prompt_policies_router)
router.include_router(runtime_config_router)
router.include_router(sandbox_sessions_router)
router.include_router(telegram_routes_router)
router.include_router(template_contexts_router)
router.include_router(templates_catalog_router)
router.include_router(user_agents_router)
router.include_router(visual_assets_router)
router.include_router(workspace_managed_draft_router)
router.include_router(workspace_projects_router)


def _gateway_effective_tenant_id(request_tenant: str | None) -> str:
    """Misma resolución que ``main._effective_tenant_id`` (p. ej. default → Marco si está en PM2)."""
    import main as gateway_main

    raw = (request_tenant or "").strip() or "default"
    return gateway_main._effective_tenant_id(raw)


class ProjectCreateBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    source_template: str = Field(
        default="default",
        description="Preset de habilidades (id de plantilla opcional). El disco siempre clona desde templates/default.",
    )
    name: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    topology: str = "general"
    system_prompt: str = ""
    soul: str = ""


class AdminLoginBody(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return (v or "").strip().lower()

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v) < 8 or len(v) > 128:
            raise ValueError("invalid password length")
        return v


async def _admin_auth_login_impl(body: Any, request: Request, response: Response) -> dict[str, Any]:
    from core.admin_auth import (
        apply_login_delay,
        check_ip_rate_limit,
        clear_email_failures,
        client_ip,
        create_session,
        record_email_failure,
        set_auth_cookies,
    )
    from duckclaw import DuckClaw
    from duckclaw import db_write_queue
    from duckclaw.admin_console_users import (
        authenticate_console_user_readonly,
        console_users_seed_required,
        default_seed_users,
    )
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.write_commands import (
        ClearAdminLoginFailuresCommand,
        RecordAdminLoginFailureCommand,
        UpdateConsoleUserPasswordHashCommand,
        UpsertConsoleUserCommand,
    )

    redis_client = getattr(request.app.state, "redis", None)
    ip = client_ip(request)
    if redis_client is not None:
        await check_ip_rate_limit(redis_client, ip)
        await apply_login_delay(redis_client, body.email)

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(503, "Gateway DuckDB no disponible", gw)

    from core.admin_identity import attach_profile_to_console_user, console_user_public

    def _enqueue_auth_command(command: Any) -> str:
        task_id = db_write_queue.enqueue_typed_command(command, db_path=gw, user_id="default")
        command_status = db_write_queue.poll_task_status_sync(task_id, timeout_sec=0.5, interval_sec=0.05)
        if command_status and command_status.status == "failed":
            raise RuntimeError(command_status.detail or "admin auth write failed")
        return task_id

    db = DuckClaw(gw, read_only=True, engine="python")
    should_seed = False
    try:
        should_seed = console_users_seed_required(db)
    finally:
        db.close()

    if should_seed:
        for seed_user in default_seed_users():
            _enqueue_auth_command(
                UpsertConsoleUserCommand(
                    tenant_id="default",
                    actor_email="system",
                    email=seed_user["email"],
                    nombre=seed_user.get("nombre") or seed_user["email"],
                    rol=seed_user.get("rol") or "user",
                    password=seed_user.get("password") or "",
                    initials=seed_user.get("initials") or "",
                    active=True,
                )
            )

    db = DuckClaw(gw, read_only=True, engine="python")
    user: dict[str, Any] | None = None
    password_update: dict[str, Any] | None = None
    try:
        user, password_update = authenticate_console_user_readonly(
            db, email=body.email, password=body.password
        )
        if user:
            user = attach_profile_to_console_user(db, user)
    finally:
        db.close()

    if not user:
        try:
            _enqueue_auth_command(
                RecordAdminLoginFailureCommand(
                    tenant_id="default",
                    actor_email="system",
                    email=body.email,
                )
            )
        except RuntimeError as exc:
            raise _problem(503, "DB-writer rechazó fallo de login", str(exc)) from exc
        if redis_client is not None:
            await record_email_failure(redis_client, body.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    try:
        if password_update:
            _enqueue_auth_command(
                UpdateConsoleUserPasswordHashCommand(
                    tenant_id="default",
                    actor_email=str(user.get("email") or "system"),
                    email=str(password_update.get("email") or body.email),
                    password_hash=str(password_update.get("password_hash") or ""),
                    hash_algo=str(password_update.get("hash_algo") or "argon2id"),
                    hash_params=dict(password_update.get("hash_params") or {}),
                )
            )
        _enqueue_auth_command(
            ClearAdminLoginFailuresCommand(
                tenant_id="default",
                actor_email=str(user.get("email") or "system"),
                email=body.email,
            )
        )
    except RuntimeError as exc:
        raise _problem(503, "DB-writer rechazó estado de login", str(exc)) from exc

    if redis_client is None:
        raise _problem(503, "Redis no disponible para sesiones", "redis")
    await clear_email_failures(redis_client, body.email)
    session_id, csrf_token = await create_session(redis_client, user=user)
    set_auth_cookies(response, session_id, csrf_token, request=request)
    logging.getLogger(__name__).info("login_success email=%s ip=%s", body.email, ip)
    return {"user": console_user_public(user)}


@router.post("/projects", dependencies=[Depends(_require_admin_key)])
async def create_project(
    body: ProjectCreateBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", body.id.strip())
    if not wid:
        raise _problem(400, "id inválido", body.id)
    dest = _create_worker_from_source(
        wid=wid,
        source_template=body.source_template,
        name=body.name,
        description=body.description,
        skills=body.skills,
        topology=body.topology,
        system_prompt=body.system_prompt,
        soul=body.soul,
    )
    _admin_audit(
        "project.create",
        f"templates/{wid}",
        body.source_template,
        actor=actor,
        meta={"skills": body.skills, "path": str(dest.relative_to(_repo_root()))},
    )
    return {"ok": True, "id": wid, "path": str(dest.relative_to(_repo_root()))}


from routers.admin_db_first import router as _admin_db_first_router  # noqa: E402
from routers.reports import router as _admin_reports_router  # noqa: E402

router.include_router(_admin_db_first_router)
router.include_router(_admin_reports_router)
