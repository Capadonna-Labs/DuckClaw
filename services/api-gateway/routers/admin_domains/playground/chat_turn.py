"""Lógica compartida de turno chat/voz para admin playground."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from core.agent_chat import invoke_chat, invoke_chat_sse_body
from core.chat_visual_artifacts import admin_visual_fields_from_invoke_result
from core.models import ChatRequest
from duckclaw.channels import GatewayDeliveryContext
from routers.admin_domains.admin_common import admin_audit, problem
from routers.admin_domains.playground.project_rag_context import project_context_message
from routers.admin_domains.playground.schemas import PlaygroundChatBody, PlaygroundImageIn
from routers.admin_domains.playground.team_context import (
    playground_team_context,
    playground_worker_allowed_in_team,
    playground_worker_explicitly_in_team,
)
from routers.admin_domains.playground.tenant_resolution import gateway_effective_tenant_id
from routers.admin_domains.playground.vault_access import resolved_vault_for_admin_chat


@dataclass
class PlaygroundActorTurn:
    wid: str
    project_id: str
    eff_tenant: str
    profile: dict[str, Any]
    catalog_allowed: bool
    project_context: dict[str, Any] | None


def resolve_playground_actor_turn(
    actor: str,
    *,
    worker_id: str,
    project_id: str | None,
) -> PlaygroundActorTurn:
    from core.admin_identity import (
        get_visible_worker_for_actor,
        open_gateway_db,
        project_context_for_actor,
        resolve_playground_worker_for_project,
    )
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    project_id_clean = (project_id or "").strip()
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", worker_id.strip()) or "default"
    profile: dict[str, Any] = {
        "email": actor,
        "tenant_id": gateway_effective_tenant_id("default"),
        "telegram_user_id": "",
    }
    catalog_allowed = False
    project_context: dict[str, Any] | None = None
    try:
        with open_gateway_db(read_only=True) as db:
            profile = ensure_profile_for_user(db, email=actor)
            if wid == "default" or get_visible_worker_for_actor(db, actor_email=actor, worker_id=wid):
                catalog_allowed = True
                try:
                    wid, project_id_clean = resolve_playground_worker_for_project(
                        db,
                        actor_email=actor,
                        project_id=project_id_clean,
                        worker_id=wid,
                    )
                    if project_id_clean:
                        project_context = project_context_for_actor(
                            db,
                            actor_email=actor,
                            project_id=project_id_clean,
                        )
                except PermissionError as exc:
                    raise problem(403, str(exc), wid) from exc
    except FileNotFoundError:
        pass
    eff_tenant = str(profile.get("tenant_id") or "").strip() or gateway_effective_tenant_id("default")
    return PlaygroundActorTurn(
        wid=wid,
        project_id=project_id_clean,
        eff_tenant=eff_tenant,
        profile=profile,
        catalog_allowed=catalog_allowed,
        project_context=project_context,
    )


def enforce_playground_worker_access(
    *,
    wid: str,
    catalog_allowed: bool,
    team_ctx: dict[str, Any],
    actor: str,
    request: Request,
) -> None:
    console_actor = (request.headers.get("x-duckclaw-actor") or "").strip()
    db_first_console = bool(
        (actor or "").strip().lower() not in ("", "admin-ui")
        or (console_actor and console_actor.lower() not in ("admin-ui", ""))
    )
    explicit_team = playground_worker_explicitly_in_team(team_ctx, wid)
    team_allowed = playground_worker_allowed_in_team(team_ctx, wid)
    if wid != "default" and not catalog_allowed:
        raise problem(403, "Worker no asignado al catálogo del actor", wid)
    if not catalog_allowed:
        if db_first_console:
            if (team_ctx.get("team_source") or "") == "all":
                raise problem(403, "Worker no asignado al catálogo del actor", wid)
            if not explicit_team:
                raise problem(403, "Worker no asignado al catálogo del actor", wid)
        elif not team_allowed:
            raise problem(403, "Worker no asignado al catálogo del actor", wid)


async def ingest_playground_message_with_images(
    msg: str,
    images: list[PlaygroundImageIn],
    *,
    eff_tenant: str,
) -> str:
    from core.comfyui_inbound import ingest_admin_visual_edit_inbound, should_route_comfyui_edit
    from core.vlm_ingest import decode_admin_image_b64, enrich_message_with_admin_images

    if should_route_comfyui_edit(has_visual=True, caption=msg):
        first_image = images[0]
        try:
            return ingest_admin_visual_edit_inbound(
                image_bytes=decode_admin_image_b64(first_image.data_base64),
                caption=msg,
                tenant_id=eff_tenant,
                mime_type=first_image.mime_type,
            )
        except ValueError as exc:
            raise problem(400, str(exc), "images") from exc
        except Exception as exc:
            raise problem(502, "Error preparando imagen para edición", str(exc)) from exc
    try:
        return await enrich_message_with_admin_images(
            msg,
            [img.model_dump() for img in images],
        )
    except ValueError as exc:
        raise problem(400, str(exc), "images") from exc
    except Exception as exc:
        raise problem(502, "Error procesando imagen (VLM)", str(exc)) from exc


@dataclass
class PlaygroundPreparedChat:
    wid: str
    project_id: str
    eff_tenant: str
    msg: str
    original_user_message: str | None
    session_id: str
    guard_user_id: str
    vault_path: str
    rag_context_count: int
    chat: ChatRequest


async def prepare_playground_chat_turn(
    body: PlaygroundChatBody,
    *,
    actor: str,
    request: Request,
    telegram_user_id_override: str | None = None,
) -> PlaygroundPreparedChat:
    turn = resolve_playground_actor_turn(
        actor,
        worker_id=body.worker_id,
        project_id=body.project_id,
    )
    msg = (body.message or "").strip()
    original_user_message = ((body.user_incoming or "").strip() or msg)
    if not msg and not body.images:
        raise problem(400, "message o images requeridos", "")
    if body.images:
        msg = await ingest_playground_message_with_images(msg, body.images, eff_tenant=turn.eff_tenant)
    if not msg:
        raise problem(400, "message vacío tras VLM", body.message)

    team_ctx = playground_team_context(
        telegram_user_id=turn.profile.get("telegram_user_id") or telegram_user_id_override or body.telegram_user_id,
        tenant_id=turn.eff_tenant,
        chat_id=body.chat_id,
    )
    enforce_playground_worker_access(
        wid=turn.wid,
        catalog_allowed=turn.catalog_allowed,
        team_ctx=team_ctx,
        actor=actor,
        request=request,
    )

    session_id = (body.chat_id or "admin-playground").strip() or "admin-playground"
    if body.images:
        admin_audit(
            "playground.chat.images",
            session_id,
            f"count={len(body.images)}",
            actor=actor,
        )
    owner_uid = str(team_ctx.get("telegram_user_id") or "").strip()
    guard_user_id = owner_uid or (actor or "admin-ui")

    vault_info = await resolved_vault_for_admin_chat(
        session_id,
        team_ctx,
        turn.wid,
        body_override=(body.vault_db_path or "").strip() or None,
        request=request,
    )
    vault_path = vault_info.get("effective_path") or ""
    rag_context_count = 0
    if turn.project_context:
        msg, rag_context_count = project_context_message(
            msg=msg,
            project_context=turn.project_context,
            worker_id=turn.wid,
            tenant_id=turn.eff_tenant,
            project_id=turn.project_id,
        )

    chat = ChatRequest(
        message=msg,
        user_incoming=original_user_message or None,
        chat_id=session_id,
        user_id=guard_user_id,
        username=actor or guard_user_id,
        chat_type="private",
        tenant_id=turn.eff_tenant,
        project_id=turn.project_id,
        stream=body.stream,
        vault_db_path=vault_path or None,
    )
    return PlaygroundPreparedChat(
        wid=turn.wid,
        project_id=turn.project_id,
        eff_tenant=turn.eff_tenant,
        msg=msg,
        original_user_message=original_user_message,
        session_id=session_id,
        guard_user_id=guard_user_id,
        vault_path=vault_path,
        rag_context_count=rag_context_count,
        chat=chat,
    )


async def prepare_playground_voice_turn(
    *,
    actor: str,
    worker_id: str,
    chat_id: str,
    project_id: str | None,
    msg: str,
    request: Request,
) -> PlaygroundPreparedChat:
    turn = resolve_playground_actor_turn(actor, worker_id=worker_id, project_id=project_id)
    team_ctx = playground_team_context(tenant_id=turn.eff_tenant, chat_id=chat_id)
    if turn.wid != "default" and not turn.catalog_allowed:
        raise problem(403, "Worker no asignado al catálogo del actor", turn.wid)

    session_id = (chat_id or "admin-playground").strip() or "admin-playground"
    owner_uid = str(team_ctx.get("telegram_user_id") or "").strip()
    guard_user_id = owner_uid or (actor or "admin-ui")

    vault_info = await resolved_vault_for_admin_chat(session_id, team_ctx, turn.wid, request=request)
    vault_path = vault_info.get("effective_path") or ""
    rag_context_count = 0
    if turn.project_context:
        msg, rag_context_count = project_context_message(
            msg=msg,
            project_context=turn.project_context,
            worker_id=turn.wid,
            tenant_id=turn.eff_tenant,
            project_id=turn.project_id,
        )

    chat = ChatRequest(
        message=msg,
        chat_id=session_id,
        user_id=guard_user_id,
        username=actor or guard_user_id,
        chat_type="private",
        tenant_id=turn.eff_tenant,
        project_id=turn.project_id,
        stream=False,
        vault_db_path=vault_path or None,
    )
    return PlaygroundPreparedChat(
        wid=turn.wid,
        project_id=turn.project_id,
        eff_tenant=turn.eff_tenant,
        msg=msg,
        original_user_message=None,
        session_id=session_id,
        guard_user_id=guard_user_id,
        vault_path=vault_path,
        rag_context_count=rag_context_count,
        chat=chat,
    )


def playground_wants_stream(body: PlaygroundChatBody, request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    return bool(body.stream) or "text/event-stream" in accept


def playground_streaming_response(
    prepared: PlaygroundPreparedChat,
    *,
    request: Request,
    voice_response: bool,
) -> StreamingResponse:
    from core.sse_stream import SSE_HEADERS

    redis_client = getattr(request.app.state, "redis", None)
    delivery_context = GatewayDeliveryContext.trusted_admin_console()
    return StreamingResponse(
        invoke_chat_sse_body(
            prepared.chat,
            prepared.wid,
            prepared.session_id,
            prepared.eff_tenant,
            redis_client=redis_client,
            delivery_context=delivery_context,
            http_request=request,
            voice_response=voice_response,
            invoke_chat=invoke_chat,
        ),
        media_type="text/event-stream",
        headers=dict(SSE_HEADERS),
    )


async def invoke_playground_chat_sync(
    prepared: PlaygroundPreparedChat,
    *,
    request: Request,
) -> Any:
    redis_client = getattr(request.app.state, "redis", None)
    delivery_context = GatewayDeliveryContext.trusted_admin_console()
    try:
        return await invoke_chat(
            prepared.chat,
            prepared.wid,
            session_id=prepared.session_id,
            tenant_id=prepared.eff_tenant,
            redis_client=redis_client,
            delivery_context=delivery_context,
        )
    except Exception as exc:
        raise problem(500, "Error en playground chat", str(exc)) from exc


def format_playground_chat_payload(
    prepared: PlaygroundPreparedChat,
    result: Any,
) -> dict[str, Any]:
    if isinstance(result, dict):
        visual = admin_visual_fields_from_invoke_result(
            prepared.session_id,
            result,
            prepared.eff_tenant,
        )
        payload: dict[str, Any] = {
            "ok": True,
            "worker_id": prepared.wid,
            "project_id": prepared.project_id or None,
            "response": str(result.get("response") or result.get("reply") or ""),
            "assigned_worker_id": result.get("assigned_worker_id"),
            "usage_tokens": result.get("usage_tokens"),
            "rag_context_count": prepared.rag_context_count,
        }
        if visual:
            payload.update(visual)
        return payload
    return {"ok": True, "worker_id": prepared.wid, "response": str(result or "")}


def extract_playground_reply(result: Any) -> str:
    if isinstance(result, dict):
        return str(result.get("response") or result.get("reply") or "").strip()
    return str(result or "").strip()


def admin_visual_from_result(session_id: str, result: Any, tenant_id: str) -> dict[str, Any]:
    return admin_visual_fields_from_invoke_result(session_id, result, tenant_id)
