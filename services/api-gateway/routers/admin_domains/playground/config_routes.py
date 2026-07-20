"""Rutas de configuración LLM, vault y worker del admin playground."""

from __future__ import annotations

import os
import re
from typing import Any

from fastapi import Depends, Query, Request

import duckclaw.db_write_queue as db_write_queue
from duckclaw.commands.model_setup import _DEFAULT_BASE_URL_BY_PROVIDER, _DEFAULT_MODEL_BY_PROVIDER, _PROVIDERS
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.integrations.llm_providers import coerce_mlx_llm_model, mlx_openai_compatible_base_url
from duckclaw.runtime_session_settings import RUNTIME_SESSION_DOMAIN, runtime_session_actor
from duckclaw.write_commands import UpsertRuntimeSettingCommand
from routers.admin_domains.admin_common import actor_from_header, problem, repo_root, require_admin_key
from routers.admin_domains.env_config import env_file
from routers.admin_domains.playground.llm_settings import (
    playground_llm_catalog,
    playground_realtime_voice_status,
    playground_runtime_defaults,
    playground_voice_status,
    resolved_llm_for_chat,
    resolved_llm_for_playground,
)
from routers.admin_domains.playground.router import router
from routers.admin_domains.playground.schemas import (
    PlaygroundKnowledgeScopeBody,
    PlaygroundModelBody,
    PlaygroundSlmBody,
    PlaygroundVaultBody,
    PlaygroundWorkerBody,
)
from routers.admin_domains.playground.slm_settings import (
    resolved_slm_for_playground_async,
    slm_base_url,
)
from routers.admin_domains.playground.team_context import merge_playground_catalog_and_team_workers, playground_team_context
from routers.admin_domains.playground.tenant_resolution import gateway_effective_tenant_id
from routers.admin_domains.playground.vault_access import resolved_vault_for_admin_chat
from routers.admin_domains.playground.worker_selection import (
    pick_playground_worker,
    playground_vault_options_for_team,
)


@router.get("/playground/config", dependencies=[Depends(require_admin_key)])
async def playground_config(
    request: Request,
    telegram_user_id: str | None = Query(None, description="ID Telegram (default: DUCKCLAW_OWNER_ID)"),
    tenant_id: str | None = Query(None, description="Tenant para whitelist y equipo"),
    chat_id: str | None = Query(
        None,
        description="Chat id para team_templates (default: mismo que telegram_user_id)",
    ),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import (
        list_projects_with_agents_for_actor,
        open_gateway_db,
        playground_workers_for_actor,
    )
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    profile: dict[str, Any] = {
        "email": actor,
        "tenant_id": gateway_effective_tenant_id("default"),
        "telegram_user_id": "",
    }
    workers_list: list[dict[str, str]] = []
    projects: list[dict[str, Any]] = []
    try:
        with open_gateway_db(read_only=True) as db:
            profile = ensure_profile_for_user(db, email=actor)
            workers_list = playground_workers_for_actor(db, actor_email=actor)
            projects = list_projects_with_agents_for_actor(db, actor_email=actor)
    except FileNotFoundError:
        pass
    team_ctx = playground_team_context(
        telegram_user_id=profile.get("telegram_user_id") or telegram_user_id,
        tenant_id=profile.get("tenant_id"),
        chat_id=chat_id,
    )
    console_actor = (request.headers.get("x-duckclaw-actor") or "").strip()
    if console_actor and console_actor.lower() not in ("admin-ui", ""):
        team_ctx["authorized"] = True
        if not team_ctx.get("whitelist_role"):
            team_ctx["whitelist_role"] = "admin-console"
    workers_list = merge_playground_catalog_and_team_workers(workers_list, team_ctx)
    if not any(str(item.get("id") or "").strip() == "default" for item in workers_list):
        # default siempre permitido (worker_allowed_for_actor); el catálogo DB puede estar vacío.
        workers_list = [{"id": "default", "label": "default"}, *workers_list]
    workers_payload = {"workers": workers_list, "workers_invalid": [], "team_hint_extra": ""}
    eff_chat = (chat_id or team_ctx.get("team_chat_id") or "admin-playground").strip()
    eff_tenant = str(profile.get("tenant_id") or "").strip() or gateway_effective_tenant_id("default")
    runtime_defaults = playground_runtime_defaults(eff_tenant, str(profile.get("email") or actor))
    llm = resolved_llm_for_playground(
        chat_id=eff_chat,
        tenant_id=eff_tenant,
        actor_email=str(profile.get("email") or actor),
    )
    catalog: list[dict[str, Any]] = []
    llm_gap: dict[str, str] | None = None
    actor_email = str(profile.get("email") or actor)
    try:
        with open_gateway_db(read_only=True) as db:
            from duckclaw.llm_bootstrap import build_llm_gap

            catalog = playground_llm_catalog(
                llm.get("provider", ""),
                db=db,
                tenant_id=eff_tenant,
                actor_email=actor_email,
            )
            llm_gap = build_llm_gap(
                db,
                provider=llm.get("provider", ""),
                tenant_id=eff_tenant,
                actor_email=actor_email,
            )
    except FileNotFoundError:
        catalog = playground_llm_catalog(
            llm.get("provider", ""),
            tenant_id=eff_tenant,
            actor_email=actor_email,
        )
    team_hint = (team_ctx.get("team_hint") or "") + workers_payload.get("team_hint_extra", "")
    selected_worker_id = ""
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is not None and eff_chat:
        from core.admin_conversations import resolve_conversation_view

        _, conv_meta, _ = await resolve_conversation_view(redis_client, eff_tenant, eff_chat)
        if conv_meta is not None:
            selected_worker_id = (
                (conv_meta.preferred_worker_id or conv_meta.last_worker_id or "").strip()
            )
    if not selected_worker_id:
        runtime_worker = re.sub(r"[^a-zA-Z0-9_-]", "", runtime_defaults.get("default_worker_id", ""))
        visible_worker_ids = {str(item.get("id") or "").strip() for item in workers_payload["workers"]}
        if runtime_worker and runtime_worker in visible_worker_ids:
            selected_worker_id = runtime_worker
    default_wid = pick_playground_worker(team_ctx, selected_worker_id or None)
    vault = await resolved_vault_for_admin_chat(
        eff_chat,
        team_ctx,
        default_wid,
        request=request,
        runtime_default_vault=runtime_defaults.get("default_vault_db_path"),
    )
    vault_options = playground_vault_options_for_team(team_ctx)
    voice = await playground_voice_status()
    realtime_voice = await playground_realtime_voice_status()
    knowledge_scope = "platform"
    try:
        with open_gateway_db(read_only=True) as db:
            from routers.admin_domains.playground.knowledge_scope_resolution import (
                resolve_playground_knowledge_scope,
            )

            knowledge_scope = resolve_playground_knowledge_scope(
                db,
                chat_id=eff_chat,
                tenant_id=eff_tenant,
                project_id="",
            )
    except FileNotFoundError:
        pass
    slm = await resolved_slm_for_playground_async(
        chat_id=eff_chat,
        tenant_id=eff_tenant,
        repo_root=repo_root(),
    )
    return {
        "llm": llm,
        "llm_gap": llm_gap,
        "slm": slm,
        "catalog": catalog,
        "config_chat_id": eff_chat,
        "knowledge_scope": knowledge_scope,
        "workers": workers_payload["workers"],
        "workers_invalid": workers_payload["workers_invalid"],
        "env_path": str(env_file()),
        "effective_tenant_id": eff_tenant,
        "telegram_user_id": (profile.get("telegram_user_id") or team_ctx.get("telegram_user_id") or ""),
        "team_chat_id": team_ctx.get("team_chat_id"),
        "projects": projects,
        "authorized": team_ctx.get("authorized"),
        "whitelist_role": team_ctx.get("whitelist_role"),
        "team_source": team_ctx.get("team_source"),
        "team_hint": team_hint.strip(),
        "vault": vault,
        "vault_options": vault_options,
        "selected_worker_id": selected_worker_id or default_wid,
        "voice": voice,
        "realtime_voice": realtime_voice,
        "chat_endpoint": "/api/v1/admin/playground/chat",
        "chat_stream_endpoint": "/api/v1/admin/playground/chat",
        "chat_stream_hint": "POST con stream=true o Accept: text/event-stream",
        "note": (
            "Proveedor y bóveda DuckDB por conversación. "
            "Sin override de bóveda, usa vault activo del usuario o manifest del worker."
        ),
    }


@router.put("/playground/vault", dependencies=[Depends(require_admin_key)])
async def playground_set_vault(
    body: PlaygroundVaultBody,
    request: Request,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    """Persiste bóveda DuckDB por conversación (admin UI)."""
    from core.admin_conversations import get_conversation_meta, patch_conversation_vault, upsert_conversation_meta
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    chat_id = body.chat_id.strip()
    tenant_id = gateway_effective_tenant_id((body.tenant_id or "default").strip() or "default")
    try:
        with open_gateway_db(read_only=True) as db:
            profile = ensure_profile_for_user(db, email=actor)
            tenant_id = str(profile.get("tenant_id") or "").strip() or tenant_id
    except FileNotFoundError:
        pass
    raw_path = (body.vault_db_path or "").strip()
    if raw_path:
        from duckclaw.gateway_db import resolve_env_duckdb_path

        abs_path = resolve_env_duckdb_path(raw_path)
        if not os.path.isabs(abs_path):
            abs_path = str(repo_root() / abs_path.lstrip("/"))
        if not os.path.isfile(abs_path):
            raise problem(404, "Vault no encontrado", raw_path)
        stored = raw_path
    else:
        stored = ""

    redis_client = getattr(request.app.state, "redis", None)
    meta = await get_conversation_meta(redis_client, tenant_id, chat_id)
    if meta is None:
        await upsert_conversation_meta(
            redis_client,
            tenant_id=tenant_id,
            session_id=chat_id,
            title="",
            message_count=0,
        )
    meta = await patch_conversation_vault(redis_client, tenant_id, chat_id, stored or None)
    team_ctx = playground_team_context(tenant_id=tenant_id, chat_id=chat_id)
    wid = pick_playground_worker(team_ctx, None)
    vault = await resolved_vault_for_admin_chat(chat_id, team_ctx, wid, request=request)
    if stored and (meta is None or vault.get("scope") != "chat"):
        from duckclaw.gateway_db import resolve_env_duckdb_path

        vault = {
            "effective_path": resolve_env_duckdb_path(stored),
            "scope": "chat",
            "override_path": stored,
            "default_path": vault.get("default_path"),
        }
    return {
        "ok": True,
        "chat_id": chat_id,
        "tenant_id": tenant_id,
        "vault_db_path": stored,
        "vault": vault,
    }


@router.put("/playground/worker", dependencies=[Depends(require_admin_key)])
async def playground_set_worker(
    body: PlaygroundWorkerBody,
    request: Request,
) -> dict[str, Any]:
    """Persiste worker preferido por conversación (admin UI)."""
    from core.admin_conversations import (
        get_conversation_meta,
        patch_conversation_worker,
        upsert_conversation_meta,
    )

    chat_id = body.chat_id.strip()
    tenant_id = gateway_effective_tenant_id((body.tenant_id or "default").strip() or "default")
    worker_id = re.sub(r"[^a-zA-Z0-9_-]", "", (body.worker_id or "").strip())
    if not worker_id:
        raise problem(400, "worker_id inválido", body.worker_id)

    redis_client = getattr(request.app.state, "redis", None)
    meta = await get_conversation_meta(redis_client, tenant_id, chat_id)
    if meta is None:
        await upsert_conversation_meta(
            redis_client,
            tenant_id=tenant_id,
            session_id=chat_id,
            title="",
            message_count=0,
            last_worker_id=worker_id,
        )
    meta = await patch_conversation_worker(redis_client, tenant_id, chat_id, worker_id)
    team_ctx = playground_team_context(tenant_id=tenant_id, chat_id=chat_id)
    selected = (meta.preferred_worker_id if meta else worker_id) or worker_id
    return {
        "ok": True,
        "chat_id": chat_id,
        "tenant_id": tenant_id,
        "worker_id": worker_id,
        "selected_worker_id": selected,
        "effective_worker_id": pick_playground_worker(team_ctx, selected),
    }


@router.put("/playground/knowledge-scope", dependencies=[Depends(require_admin_key)])
async def playground_set_knowledge_scope(
    body: PlaygroundKnowledgeScopeBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    """Persiste alcance RAG por conversación (platform | project | both)."""
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.knowledge_scope import VALID_KNOWLEDGE_SCOPES, normalize_knowledge_scope
    from routers.admin_domains.playground.knowledge_scope_resolution import (
        resolve_playground_knowledge_scope,
    )

    raw_scope = (body.knowledge_scope or "").strip().lower()
    if raw_scope not in VALID_KNOWLEDGE_SCOPES:
        raise problem(400, "Alcance RAG inválido", "Válidos: platform, project, both")

    chat_id = body.chat_id.strip()
    project_id = (body.project_id or "").strip()
    tenant_id = gateway_effective_tenant_id((body.tenant_id or "default").strip() or "default")
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise problem(503, "Gateway DuckDB no disponible", "Configura DUCKCLAW_GATEWAY_DB_PATH")

    effective = normalize_knowledge_scope(raw_scope, project_id=project_id)
    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)
        tenant_id = str(profile.get("tenant_id") or "").strip() or tenant_id

    command = UpsertRuntimeSettingCommand(
        tenant_id=tenant_id,
        actor_email=runtime_session_actor(chat_id),
        domain=RUNTIME_SESSION_DOMAIN,
        key="knowledge_scope",
        value=effective,
        value_kind="string",
        updated_by=actor,
    )
    try:
        from duckclaw.gateway_enqueue import enqueue_admin_command

        task_id = enqueue_admin_command(command)
    except Exception as exc:
        raise problem(400, "No se pudo actualizar el alcance RAG", str(exc)) from exc

    with open_gateway_db(read_only=True) as db:
        resolved = resolve_playground_knowledge_scope(
            db,
            chat_id=chat_id,
            tenant_id=tenant_id,
            project_id=project_id,
            body_scope=effective,
        )
    return {
        "ok": True,
        "queued": True,
        "task_id": task_id,
        "chat_id": chat_id,
        "tenant_id": tenant_id,
        "knowledge_scope": resolved,
        "project_id": project_id or None,
        "message": f"Alcance RAG: {resolved}",
    }


@router.put("/playground/model", dependencies=[Depends(require_admin_key)])
async def playground_set_model(
    body: PlaygroundModelBody,
    request: Request,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    """Equivalente a `/model provider=…` para la consola admin."""
    prov = body.provider.strip().lower()
    if prov in ("or", "router"):
        prov = "openrouter"
    if prov not in _PROVIDERS:
        raise problem(
            400,
            "Proveedor inválido",
            f"Válidos: {', '.join(_PROVIDERS)}",
        )
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise problem(503, "Gateway DuckDB no disponible", "Configura DUCKCLAW_GATEWAY_DB_PATH")
    chat_id = body.chat_id.strip()
    if prov == "mlx":
        default_model = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
        default_base_url = mlx_openai_compatible_base_url()
        raw_model = (body.model or "").strip() if body.model is not None else default_model
        model_value = coerce_mlx_llm_model(raw_model or default_model)
    else:
        default_model = _DEFAULT_MODEL_BY_PROVIDER.get(prov, "")
        default_base_url = _DEFAULT_BASE_URL_BY_PROVIDER.get(prov, "")
        model_value = (body.model or "").strip() if body.model is not None else default_model
    base_url_value = (body.base_url or "").strip() if body.base_url is not None else default_base_url

    task_ids: list[str] = []
    for key, value in (
        ("llm_provider", prov),
        ("llm_model", model_value),
        ("llm_base_url", base_url_value),
    ):
        command = UpsertRuntimeSettingCommand(
            tenant_id="default",
            actor_email=runtime_session_actor(chat_id),
            domain=RUNTIME_SESSION_DOMAIN,
            key=key,
            value=str(value or "")[:8192],
            value_kind="string",
            updated_by=actor,
        )
        try:
            from duckclaw.gateway_enqueue import enqueue_admin_command

            task_id = enqueue_admin_command(command)
        except Exception as exc:
            raise problem(400, "No se pudo actualizar el modelo", str(exc)) from exc
        task_ids.append(task_id)

    llm = resolved_llm_for_chat(chat_id)
    catalog: list[dict[str, Any]] = []
    llm_gap: dict[str, str] | None = None
    try:
        from core.admin_identity import open_gateway_db
        from duckclaw.llm_bootstrap import build_llm_gap

        with open_gateway_db(read_only=True) as db:
            catalog = playground_llm_catalog(
                llm.get("provider", ""),
                db=db,
                tenant_id="default",
                actor_email=runtime_session_actor(chat_id),
            )
            llm_gap = build_llm_gap(
                db,
                provider=llm.get("provider", ""),
                tenant_id="default",
                actor_email=runtime_session_actor(chat_id),
            )
    except FileNotFoundError:
        catalog = playground_llm_catalog(llm.get("provider", ""))
    return {
        "ok": True,
        "queued": True,
        "task_id": task_ids[0] if task_ids else "",
        "task_ids": task_ids,
        "message": "✅ Modelo actualizado. Los próximos mensajes usarán esta config.",
        "chat_id": chat_id,
        "llm": llm,
        "catalog": catalog,
        "llm_gap": llm_gap,
    }


@router.put("/playground/slm", dependencies=[Depends(require_admin_key)])
async def playground_set_slm(
    body: PlaygroundSlmBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    """Persiste SLM opcional (MLX-Inference) por conversación."""
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise problem(503, "Gateway DuckDB no disponible", "Configura DUCKCLAW_GATEWAY_DB_PATH")
    chat_id = body.chat_id.strip()
    adapter_value = (body.adapter_path or "").strip()
    base_url_value = slm_base_url()
    enabled_value = "true" if body.enabled else "false"

    task_ids: list[str] = []
    for key, value in (
        ("slm_enabled", enabled_value),
        ("slm_adapter_path", adapter_value),
        ("slm_base_url", base_url_value),
    ):
        command = UpsertRuntimeSettingCommand(
            tenant_id="default",
            actor_email=runtime_session_actor(chat_id),
            domain=RUNTIME_SESSION_DOMAIN,
            key=key,
            value=str(value or "")[:8192],
            value_kind="string",
            updated_by=actor,
        )
        try:
            from duckclaw.gateway_enqueue import enqueue_admin_command

            task_id = enqueue_admin_command(command)
        except Exception as exc:
            raise problem(400, "No se pudo actualizar el SLM", str(exc)) from exc
        task_ids.append(task_id)

    slm = await resolved_slm_for_playground_async(
        chat_id=chat_id,
        tenant_id="default",
        repo_root=repo_root(),
    )
    return {
        "ok": True,
        "queued": True,
        "task_id": task_ids[0] if task_ids else "",
        "task_ids": task_ids,
        "message": (
            "✅ SLM actualizado."
            if body.enabled
            else "SLM desactivado para esta conversación."
        ),
        "chat_id": chat_id,
        "slm": slm,
    }
