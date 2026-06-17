"""Orquestación de chat agente: invoke, SSE, rutas POST /api/v1/agent/*/chat."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import traceback
from dataclasses import replace
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from core.agent_routes import effective_tenant_id
from core.chat_auth import authorize_or_reject as _default_authorize_or_reject
from core.chat_history import (
    gateway_chat_history_enabled,
    normalize_history_item,
    normalize_history_list,
    redis_load_chat_history,
    redis_save_chat_history,
)
from core.chat_locks import maybe_chat_lock_for_request
from core.chat_reply_format import (
    beautify_structured_insight_telegram,
    chat_identity_label,
    clean_agent_response,
    strip_false_chart_delivery_lines,
    strip_markdown_bold,
    truncate_log,
)
from core.chat_visual_artifacts import (
    admin_visual_fields_from_invoke_result,
    persist_admin_fly_charts,
)
from core.fly_command_invocation import invoke_legacy_fly_command
from core.gateway_vault import dedicated_gateway_vault_db_path
from core.models import ChatRequest
from core.sandbox_figure_b64 import decode_sandbox_figure_base64, decode_valid_sandbox_image_bytes
from core.telegram_chunking import (
    TELEGRAM_SENDMESSAGE_CHAR_LIMIT,
    plain_subchunks_for_telegram_budget,
    split_plain_text_for_telegram_reply,
    telegram_reply_plain_chunk_size,
)
from core.telegram_delivery import (
    deliver_outbound_by_channel,
    effective_telegram_bot_token,
    strip_lines_mentioning_workspace_output,
)
from core.telegram_media_upload import send_sandbox_chart_to_telegram_sync
from duckclaw.channels import GatewayDeliveryContext
from duckclaw.forge.team_env import default_worker_id_from_env
from duckclaw.gateway_db import resolve_env_duckdb_path
from duckclaw.utils.logger import (
    format_chat_id_for_terminal,
    get_obs_logger,
    log_err,
    log_req,
    log_res,
    set_log_context,
)
from duckclaw.utils.telegram_markdown_v2 import (
    llm_markdown_to_telegram_html,
    unescape_telegram_markdown_v2_layers,
)
from duckclaw.vaults import resolve_active_vault, vault_scope_id_for_tenant

try:
    from core.config import settings
except ImportError:
    from duckclaw.gateway.settings import get_gateway_settings

    settings = get_gateway_settings()

_gateway_log = logging.getLogger("duckclaw.gateway")
_obs_log = get_obs_logger()

router = APIRouter(tags=["agent"])


def _resolve_authorize_or_reject():
    """Compat tests: ``monkeypatch.setattr(main, '_authorize_or_reject', ...)``."""
    import sys

    main_mod = sys.modules.get("main")
    if main_mod is not None:
        fn = getattr(main_mod, "_authorize_or_reject", None)
        if fn is not None and fn is not _default_authorize_or_reject:
            return fn
    return _default_authorize_or_reject


def resolve_chat_session_id(body: ChatRequest, req: Request) -> tuple[str, str]:
    """
    Identificador de hilo para estado por chat (sandbox, /team, auditoría).

    Orden: cuerpo JSON (chat_id y alias Pydantic) → query ?chat_id= / ?session_id=
    → cabeceras X-Chat-Id, X-Session-Id, X-Duckclaw-Chat-Id.
    """
    cid = (body.chat_id or "").strip()
    if cid:
        return cid, "body.chat_id"
    for key in ("chat_id", "session_id", "thread_id", "chatId"):
        raw = req.query_params.get(key)
        if raw and str(raw).strip():
            return str(raw).strip(), f"query.{key}"
    for header in ("X-Chat-Id", "X-Session-Id", "X-Duckclaw-Chat-Id"):
        raw = req.headers.get(header)
        if raw and str(raw).strip():
            return str(raw).strip(), f"header.{header}"
    return "default", "default"


async def abort_chat_invoke_task(session_id: str, invoke_task: asyncio.Task[Any]) -> None:
    from duckclaw.graphs.chat_cancel import request_chat_cancel

    request_chat_cancel(session_id)
    try:
        from duckclaw.forge.skills.comfyui_bridge import cancel_comfy_generation_for_chat

        cancel_comfy_generation_for_chat(session_id)
    except Exception:
        pass
    if not invoke_task.done():
        invoke_task.cancel()
        try:
            await invoke_task
        except Exception:
            pass


async def invoke_chat_sse_body(
    payload: ChatRequest,
    worker_id: str,
    session_id: str,
    tenant_id: str,
    *,
    http_request: Request | None = None,
    **invoke_kwargs: Any,
):
    """Generador SSE: invoca el grafo, heartbeats admin en vivo y tokens + [DONE]."""
    from core.admin_chat_heartbeat import iter_admin_heartbeats
    from core.sse_stream import (
        emit_chat_reply_sse,
        friendly_chat_error_message,
        sse_audio,
        sse_error,
        sse_heartbeat,
        sse_terminal_done,
    )
    from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

    redis_client = invoke_kwargs.get("redis_client")
    voice_response = bool(invoke_kwargs.pop("voice_response", False))
    admin_session = is_admin_ui_chat_session(session_id)
    stop = asyncio.Event()
    heartbeat_task: asyncio.Task | None = None
    heartbeat_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def _pump_admin_heartbeats() -> None:
        try:
            async for item in iter_admin_heartbeats(redis_client, session_id, stop=stop):
                await heartbeat_queue.put(item)
        except asyncio.CancelledError:
            raise

    if admin_session and redis_client is not None:
        heartbeat_task = asyncio.create_task(_pump_admin_heartbeats())

    invoke_task = asyncio.create_task(
        invoke_chat(
            payload,
            worker_id,
            session_id,
            tenant_id,
            **invoke_kwargs,
        )
    )

    try:
        from duckclaw.graphs.chat_cancel import is_chat_cancel_requested

        while not invoke_task.done():
            if http_request is not None and await http_request.is_disconnected():
                await abort_chat_invoke_task(session_id, invoke_task)
                yield sse_error("Interrumpido por el usuario.")
                yield sse_terminal_done()
                return
            if is_chat_cancel_requested(session_id):
                await abort_chat_invoke_task(session_id, invoke_task)
                yield sse_error("Interrumpido por el usuario.")
                yield sse_terminal_done()
                return
            try:
                hb = await asyncio.wait_for(heartbeat_queue.get(), timeout=0.2)
                yield sse_heartbeat(
                    str(hb.get("text") or ""),
                    kind=str(hb.get("kind") or "status"),
                    worker_id=str(hb.get("worker_id") or "") or None,
                    swarm_slot=hb.get("swarm_slot"),
                    artifact_id=str(hb.get("artifact_id") or "").strip() or None,
                    artifact_tenant_id=str(hb.get("artifact_tenant_id") or "").strip() or None,
                    tool_name=str(hb.get("tool_name") or "").strip() or None,
                    tool_phase=str(hb.get("tool_phase") or "").strip().lower() or None,
                    elapsed_ms=hb.get("elapsed_ms"),
                )
            except asyncio.TimeoutError:
                continue

        while not heartbeat_queue.empty():
            hb = heartbeat_queue.get_nowait()
            yield sse_heartbeat(
                str(hb.get("text") or ""),
                kind=str(hb.get("kind") or "status"),
                worker_id=str(hb.get("worker_id") or "") or None,
                swarm_slot=hb.get("swarm_slot"),
                artifact_id=str(hb.get("artifact_id") or "").strip() or None,
                artifact_tenant_id=str(hb.get("artifact_tenant_id") or "").strip() or None,
                tool_name=str(hb.get("tool_name") or "").strip() or None,
                tool_phase=str(hb.get("tool_phase") or "").strip().lower() or None,
                elapsed_ms=hb.get("elapsed_ms"),
            )

        result = await invoke_task
        reply = ""
        assigned: str | None = None
        usage: dict[str, Any] | None = None
        elapsed_ms: int | None = None
        sse_extra: dict[str, Any] | None = None
        if isinstance(result, dict):
            reply = str(result.get("response") or result.get("reply") or "")
            assigned = result.get("assigned_worker_id")
            usage = result.get("usage_tokens")
            raw_elapsed = result.get("elapsed_ms")
            if raw_elapsed is not None:
                try:
                    elapsed_ms = int(raw_elapsed)
                except (TypeError, ValueError):
                    elapsed_ms = None
            admin_visual = admin_visual_fields_from_invoke_result(session_id, result, tenant_id)
            if admin_visual:
                sse_extra = dict(admin_visual)
        else:
            reply = str(result or "")
        want_tts = voice_response and bool((reply or "").strip())
        async for event in emit_chat_reply_sse(
            reply,
            assigned_worker_id=assigned,
            usage_tokens=usage,
            worker_id=worker_id,
            elapsed_ms=elapsed_ms,
            extra=sse_extra,
            emit_terminal=not want_tts,
        ):
            yield event
        if want_tts:
            from core.sensory_client import (
                SensoryUnavailable,
                resolve_voice_id_for_worker,
                sensory_enabled,
                synthesize_text,
                tts_snippet_for_reply,
            )

            eff_worker = (assigned or worker_id or "").strip() or worker_id
            if sensory_enabled():
                snippet = tts_snippet_for_reply(reply)
                if snippet:
                    try:
                        voice_id = resolve_voice_id_for_worker(eff_worker)
                        tts_result = await synthesize_text(snippet, voice_id)
                        _gateway_log.getChild("admin_tts").info(
                            "sse_audio ok worker=%s format=%s b64_len=%s",
                            eff_worker,
                            tts_result.audio_format,
                            len(tts_result.audio_base64 or ""),
                        )
                        yield sse_audio(
                            audio_base64=tts_result.audio_base64,
                            audio_format=tts_result.audio_format,
                        )
                    except SensoryUnavailable as exc:
                        _gateway_log.getChild("admin_tts").warning(
                            "sse_audio unavailable worker=%s: %s", eff_worker, exc
                        )
                        yield sse_audio(audio_unavailable=True)
                    except Exception as exc:
                        _gateway_log.getChild("admin_tts").warning(
                            "sse_audio failed worker=%s: %s", eff_worker, exc
                        )
                        yield sse_audio(audio_unavailable=True)
                else:
                    yield sse_audio(audio_unavailable=True)
            else:
                yield sse_audio(audio_unavailable=True)
            yield sse_terminal_done()
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        yield sse_error(detail, status_hint=exc.status_code)
        yield sse_terminal_done()
    except Exception as exc:
        yield sse_error(friendly_chat_error_message(exc))
        yield sse_terminal_done()
    finally:
        stop.set()
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        if not invoke_task.done():
            await abort_chat_invoke_task(session_id, invoke_task)


async def invoke_chat(
    payload: ChatRequest,
    worker_id: str,
    session_id: str,
    tenant_id: str,
    *,
    redis_client: Any = None,
    telegram_multipart_tail_delivery: str | None = None,
    telegram_mcp: Any = None,
    telegram_forced_vault_db_path: str | None = None,
    outbound_telegram_bot_token: str | None = None,
    delivery_context: GatewayDeliveryContext | None = None,
):
    """
    Orquesta la llamada al grafo LangGraph a partir de un ChatRequest.

    - session_id: ya resuelto (body + query + headers); debe ser el mismo en todos los POST del hilo.
    - telegram_multipart_tail_delivery: ignorado (siempre entrega nativa) para partes 2..N del mensaje.
    - delivery_context: si se omite, se reconstruye desde kwargs ``telegram_*`` (compatibilidad).
    """
    if delivery_context is not None:
        dc = delivery_context
    else:
        dc = GatewayDeliveryContext.from_legacy_telegram(
            telegram_multipart_tail_delivery=telegram_multipart_tail_delivery,
            telegram_mcp=telegram_mcp,
            telegram_forced_vault_db_path=telegram_forced_vault_db_path,
            outbound_telegram_bot_token=outbound_telegram_bot_token,
        )
    _ch_eff = (dc.channel or "telegram").strip().lower()
    if _ch_eff == "telegram":
        _patch: dict[str, Any] = {}
        if telegram_multipart_tail_delivery is not None:
            _patch["telegram_multipart_tail_delivery"] = telegram_multipart_tail_delivery
        if telegram_mcp is not None:
            _patch["telegram_mcp"] = telegram_mcp
        if telegram_forced_vault_db_path is not None:
            _patch["telegram_forced_vault_db_path"] = telegram_forced_vault_db_path
        if outbound_telegram_bot_token is not None:
            _patch["outbound_bot_token"] = (outbound_telegram_bot_token or "").strip() or None
        if _patch:
            dc = replace(dc, **_patch)

    message = (payload.message or "").strip()
    user_incoming = (getattr(payload, "user_incoming", None) or message or "").strip()
    session_id = (session_id or "default").strip() or "default"
    from duckclaw.graphs.chat_cancel import ChatCancelledError, clear_chat_cancel

    clear_chat_cancel(session_id)
    tenant_id = effective_tenant_id(tenant_id)
    chat_type = (payload.chat_type or "private").strip().lower() or "private"
    username = (payload.username or "Usuario").strip() or "Usuario"
    user_id = (payload.user_id or "").strip()
    if not user_id and chat_type == "private":
        user_id = (session_id or "").strip()
    vault_user_id = user_id or session_id
    vault_scope = vault_scope_id_for_tenant(tenant_id)
    _, vault_db_path = resolve_active_vault(vault_user_id, vault_scope)
    _forced_v = (dc.telegram_forced_vault_db_path or "").strip()
    _payload_vault = (getattr(payload, "vault_db_path", None) or "").strip()
    _telegram_acl_for_guard: str | None = None
    if _forced_v:
        vault_db_path = resolve_env_duckdb_path(_forced_v)
        _telegram_acl_for_guard = vault_db_path
    elif _payload_vault:
        vault_db_path = resolve_env_duckdb_path(_payload_vault)
        _telegram_acl_for_guard = vault_db_path
    else:
        _ded_vault = dedicated_gateway_vault_db_path()
        if _ded_vault:
            vault_db_path = _ded_vault
    if not _forced_v and not _payload_vault:
        _route_wid = (worker_id or "").strip()
        if _route_wid:
            try:
                from duckclaw.vaults import resolve_template_vault_path
                from duckclaw.workers.manifest import load_manifest

                _spec_route = load_manifest(_route_wid)
                _tpl_path = resolve_template_vault_path(
                    _spec_route.forge_vault_binding, vault_user_id
                )
                if _tpl_path:
                    vault_db_path = _tpl_path
            except Exception:
                pass
    history = payload.history or []
    is_system_prompt = bool(payload.is_system_prompt or False)
    skip_session_lock = bool(getattr(payload, "skip_session_lock", False) or False)
    _msg_for_cb = (message or "").strip()
    _is_fly_command = _msg_for_cb.startswith("/")
    if not is_system_prompt and not skip_session_lock and not _is_fly_command:
        try:
            from harness_core.skills.emit_correction_delta import is_circuit_breaker_active

            if is_circuit_breaker_active(
                tenant_id,
                worker_id or "",
                redis_client=redis_client,
            ):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=(
                        "Meditate circuit breaker activo para este worker. "
                        "Revisa alertas admin (meditate_critical) antes de reanudar chats."
                    ),
                )
        except HTTPException:
            raise
        except Exception:
            pass
    shared_db_path = (payload.shared_db_path or "").strip() or None
    history_for_model = normalize_history_list(list(history))
    if (
        not is_system_prompt
        and redis_client is not None
        and gateway_chat_history_enabled()
        and not history_for_model
    ):
        history_for_model = await redis_load_chat_history(redis_client, tenant_id, session_id)

    chat_ident = chat_identity_label(session_id, username)
    set_log_context(tenant_id=tenant_id, worker_id="manager", chat_id=chat_ident)
    log_req(_obs_log, "%s", truncate_log(message), source="body")

    owner_user_id = (os.getenv("DUCKCLAW_OWNER_ID") or os.getenv("DUCKCLAW_ADMIN_CHAT_ID") or "").strip()
    is_owner = bool(owner_user_id and user_id and str(user_id).strip() == str(owner_user_id).strip())
    auth_policy = (dc.auth_policy or "telegram_guard").strip()
    guard_required = auth_policy not in {"trusted_admin_console", "trusted_channel_route"}
    if not is_system_prompt and guard_required:
        await _resolve_authorize_or_reject()(
            redis_client=redis_client,
            tenant_id=tenant_id,
            user_id=user_id,
            is_owner=is_owner,
            telegram_guard_acl_db_path=_telegram_acl_for_guard,
        )

    if not is_system_prompt and not is_owner:
        from core.gateway_acl_db import ReadOnlyGatewayAclDb, get_gateway_acl_duckdb
        from duckclaw.shared_db_grants import path_is_under_shared_tree, user_may_access_shared_path

        acl_db = (
            ReadOnlyGatewayAclDb(_telegram_acl_for_guard)
            if _telegram_acl_for_guard
            else get_gateway_acl_duckdb()[0]
        )
        _candidates = {s for s in ((shared_db_path or "").strip(), (os.getenv("DUCKCLAW_SHARED_DB_PATH") or "").strip()) if s}
        for candidate in _candidates:
            if not path_is_under_shared_tree(candidate):
                continue
            if not user_may_access_shared_path(
                acl_db,
                tenant_id=tenant_id,
                user_id=vault_user_id,
                shared_db_path=candidate,
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Sin permiso para acceder a la base de datos compartida configurada.",
                )

    msg_stripped = (message or "").strip()
    if not msg_stripped:
        return {
            "response": "No recibí ningún mensaje. Escribe tu consulta o comando (por ejemplo /tasks).",
            "session_id": session_id,
            "worker_id": worker_id,
            "elapsed_ms": 0,
        }
    try:
        from duckclaw.graphs.graph_server import ainvoke_manager_ephemeral
    except Exception as exc:
        _gateway_log.error(
            "graph init failed chat=%s: %s\n%s",
            format_chat_id_for_terminal(session_id),
            exc,
            traceback.format_exc(),
        )
        raise HTTPException(status_code=503, detail=f"Error inicializando el grafo: {exc}")

    _skip_lock = bool(getattr(payload, "skip_session_lock", None) or False)
    async with maybe_chat_lock_for_request(redis_client, session_id, _skip_lock):
        if msg_stripped.startswith("/"):
            fly_response = await invoke_legacy_fly_command(
                message=message,
                session_id=session_id,
                worker_id=worker_id,
                tenant_id=tenant_id,
                vault_db_path=vault_db_path,
                vault_user_id=vault_user_id,
                requester_id=user_id,
                username=username,
                delivery_context=dc,
                resolve_telegram_bot_token=effective_telegram_bot_token,
                persist_admin_fly_charts=persist_admin_fly_charts,
            )
            if fly_response is not None:
                return fly_response

        try:
            from duckclaw.graphs.graph_server import _ensure_llm_config

            _ensure_llm_config()
        except Exception as exc:
            _gateway_log.error(
                "graph init failed chat=%s: %s\n%s",
                format_chat_id_for_terminal(session_id),
                exc,
                traceback.format_exc(),
            )
            raise HTTPException(status_code=503, detail=f"Error inicializando el grafo: {exc}")

        try:
            from duckclaw.graphs.activity import set_busy, set_idle
            set_busy(session_id, task=message)
        except Exception:
            pass
        t0 = time.monotonic()
        _admin_pg_vault_prev = os.environ.get("DUCKCLAW_ADMIN_PLAYGROUND_VAULT")
        if auth_policy in {"trusted_admin_console", "trusted_channel_route"}:
            _admin_pg_vault = (_payload_vault or vault_db_path or "").strip()
            if _admin_pg_vault:
                os.environ["DUCKCLAW_ADMIN_PLAYGROUND_VAULT"] = resolve_env_duckdb_path(_admin_pg_vault)
            else:
                os.environ.pop("DUCKCLAW_ADMIN_PLAYGROUND_VAULT", None)
        try:
            try:
                result = await ainvoke_manager_ephemeral(
                    message,
                    history_for_model,
                    session_id,
                    tenant_id=tenant_id,
                    user_id=vault_user_id,
                    username=username,
                    user_incoming=user_incoming,
                    vault_db_path=vault_db_path,
                    shared_db_path=shared_db_path,
                    is_system_prompt=is_system_prompt,
                    outbound_telegram_bot_token=(dc.outbound_bot_token or "").strip() or None,
                    entry_worker_id=(worker_id or "").strip() or None,
                )
            except ChatCancelledError:
                try:
                    from duckclaw.graphs.activity import set_idle

                    set_idle(session_id)
                except Exception:
                    pass
                elapsed_cancel = int((time.monotonic() - t0) * 1000)
                return {
                    "response": "Interrumpido.",
                    "session_id": session_id,
                    "worker_id": worker_id,
                    "elapsed_ms": elapsed_cancel,
                    "interrupted": True,
                }
            except Exception as exc:
                try:
                    from duckclaw.graphs.activity import set_idle
                    set_idle(session_id)
                except Exception:
                    pass
                try:
                    from duckclaw.graphs.on_the_fly_commands import append_task_audit, get_worker_id_for_chat
                    from duckclaw.graphs.graph_server import get_db
                    db = get_db()
                    wid = get_worker_id_for_chat(db, session_id) or worker_id
                    elapsed_fail = int((time.monotonic() - t0) * 1000)
                    append_task_audit(db, session_id, wid, message, "FAILED", elapsed_fail)
                except Exception:
                    pass
                try:
                    if os.environ.get("DUCKCLAW_SAVE_CONVERSATION_TRACES", "true").strip().lower() in ("true", "1", "yes"):
                        from duckclaw.graphs.conversation_traces import append_conversation_trace
                        from duckclaw.graphs.on_the_fly_commands import get_effective_system_prompt
                        from duckclaw.graphs.graph_server import get_db
                        _db = get_db()
                        _sys = (get_effective_system_prompt(_db, worker_id) or "").strip()
                        _sys = _sys or (os.environ.get("DUCKCLAW_SYSTEM_PROMPT") or "").strip() or None
                        append_conversation_trace(
                            session_id, message, str(exc)[:8192],
                            worker_id=worker_id, elapsed_ms=elapsed_fail, status="FAILED",
                            system_prompt=_sys,
                        )
                except Exception:
                    pass
                log_err(_obs_log, "agent_chat failed: %s", exc)
                _gateway_log.error(
                    "agent_chat failed chat=%s: %s\n%s",
                    format_chat_id_for_terminal(session_id),
                    exc,
                    traceback.format_exc(),
                )
                raise HTTPException(status_code=500, detail=str(exc))
        finally:
            if _admin_pg_vault_prev is None:
                os.environ.pop("DUCKCLAW_ADMIN_PLAYGROUND_VAULT", None)
            else:
                os.environ["DUCKCLAW_ADMIN_PLAYGROUND_VAULT"] = _admin_pg_vault_prev

        try:
            from duckclaw.graphs.activity import set_idle
            set_idle(session_id)
        except Exception:
            pass
    reply_text = result.get("reply", "") if isinstance(result, dict) else (result or "")
    try:
        from duckclaw.integrations.llm_providers import sanitize_worker_reply_text

        reply_text = sanitize_worker_reply_text(reply_text or "")
    except Exception:
        pass
    try:
        reply_text = unescape_telegram_markdown_v2_layers(reply_text or "")
    except Exception:
        pass
    try:
        from duckclaw.utils.formatters import format_reddit_mcp_reply_if_applicable

        reply_text = format_reddit_mcp_reply_if_applicable(reply_text or "")
    except Exception:
        pass
    effective_worker_id = result.get("assigned_worker_id", worker_id) if isinstance(result, dict) else worker_id
    set_log_context(
        tenant_id=tenant_id,
        worker_id=effective_worker_id or worker_id,
        chat_id=chat_ident,
    )
    usage = result.get("usage_tokens") if isinstance(result, dict) else None
    tok_extra = ""
    if isinstance(usage, dict) and usage:
        tok_extra = (
            f" | 🪙 Tokens: {usage.get('total_tokens', 0)} "
            f"[P:{usage.get('input_tokens', 0)}, C:{usage.get('output_tokens', 0)}]"
        )
        try:
            from duckclaw.llm_usage_log import append_llm_usage_log
            from duckclaw.graphs.graph_server import get_db

            append_llm_usage_log(
                get_db(),
                tenant_id=tenant_id,
                session_id=session_id,
                worker_id=effective_worker_id or worker_id,
                usage=usage,
                model=(result.get("model") if isinstance(result, dict) else None),
            )
        except Exception:
            pass
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    log_res(
        _obs_log,
        "%s (⏱️ Total: %.1fs%s)",
        truncate_log(reply_text),
        elapsed_ms / 1000.0,
        tok_extra,
    )
    _gateway_log.info(
        "out(chat_id=%s): %s",
        format_chat_id_for_terminal(chat_ident, as_repr=True),
        truncate_log(reply_text),
    )
    reply_raw = reply_text or ""
    is_admin_console = (dc.auth_policy or "").strip() == "trusted_admin_console"
    if is_admin_console:
        reply_plain_for_storage = reply_raw
    else:
        reply_text = strip_markdown_bold(reply_raw)
        reply_text = clean_agent_response(reply_text)
        if re.search(r"(?im)^#+\s*\*?\*?INSIGHT:?\*?\*?\s*", reply_text or ""):
            reply_text = beautify_structured_insight_telegram(reply_text or "")
            reply_text = strip_false_chart_delivery_lines(reply_text or "")
        reply_plain_for_storage = reply_text
    chart_sent = False
    if not is_system_prompt and isinstance(result, dict):
        photo_b64 = (result.get("sandbox_photo_base64") or "").strip()
        if photo_b64:
            png_bytes = decode_valid_sandbox_image_bytes(photo_b64)
            if not png_bytes:
                raw_try = decode_sandbox_figure_base64(photo_b64)
                _gateway_log.warning(
                    "sandbox chart: base64 no produce PNG/JPEG válido (b64_len=%s, decoded_len=%s, mod4=%s)",
                    len(photo_b64),
                    len(raw_try),
                    len("".join(photo_b64.split())) % 4,
                )
            if png_bytes and (dc.channel or "telegram").strip().lower() == "telegram":
                token = (dc.outbound_bot_token or "").strip() or effective_telegram_bot_token()
                if token:
                    loop = asyncio.get_running_loop()
                    chart_sent = bool(
                        await loop.run_in_executor(
                            None,
                            lambda: send_sandbox_chart_to_telegram_sync(
                                bot_token=token,
                                chat_id=str(session_id),
                                image_bytes=png_bytes,
                            ),
                        )
                    )
                if not chart_sent and not token:
                    _gateway_log.warning(
                        "sandbox chart: hay PNG del sandbox pero no hay token de salida para este request "
                        "(outbound_bot_token ni token efectivo del contexto)."
                    )
    if chart_sent:
        reply_plain_for_storage = strip_lines_mentioning_workspace_output(reply_plain_for_storage or "")
    try:
        if not result.get("_audit_done"):
            from duckclaw.graphs.on_the_fly_commands import append_task_audit, get_worker_id_for_chat
            from duckclaw.graphs.graph_server import get_db
            db = get_db()
            wid = get_worker_id_for_chat(db, session_id) or worker_id
            plan_title = result.get("plan_title") if isinstance(result, dict) else None
            append_task_audit(db, session_id, wid, message, "SUCCESS", elapsed_ms, plan_title=plan_title)
    except Exception:
        pass
    try:
        if os.environ.get("DUCKCLAW_SAVE_CONVERSATION_TRACES", "true").strip().lower() in ("true", "1", "yes"):
            from duckclaw.graphs.conversation_traces import append_conversation_trace
            from duckclaw.graphs.on_the_fly_commands import get_effective_system_prompt
            from duckclaw.graphs.graph_server import get_db
            trace_messages = result.get("messages") if isinstance(result, dict) else None
            db = get_db()
            system_from_prompt = (get_effective_system_prompt(db, effective_worker_id) or "").strip()
            system_for_trace = system_from_prompt or (os.environ.get("DUCKCLAW_SYSTEM_PROMPT") or "").strip() or None
            append_conversation_trace(
                session_id, message, reply_plain_for_storage or "",
                worker_id=effective_worker_id, elapsed_ms=elapsed_ms, status="SUCCESS",
                system_prompt=system_for_trace,
                messages=trace_messages,
            )
    except Exception:
        pass
    _telegram_response_parts_count = 1
    telegram_reply_head_plain: str | None = None
    telegram_multipart_tail_plain_for_client: str | None = None
    try:
        coarse = split_plain_text_for_telegram_reply(
            reply_plain_for_storage or "",
            telegram_reply_plain_chunk_size(),
        )
        plain_parts: list[str] = []
        for piece in coarse:
            plain_parts.extend(plain_subchunks_for_telegram_budget(piece, llm_markdown_to_telegram_html))
        if not plain_parts:
            plain_parts = [""]
        _telegram_response_parts_count = len(plain_parts)
        tail_plain = "\n\n".join(plain_parts[1:]) if len(plain_parts) > 1 else ""
        if tail_plain.strip():
            telegram_reply_head_plain = plain_parts[0]
            telegram_multipart_tail_plain_for_client = tail_plain
    except Exception:
        try:
            reply_text = llm_markdown_to_telegram_html(reply_plain_for_storage or "")
            cap = TELEGRAM_SENDMESSAGE_CHAR_LIMIT - 16
            if len(reply_text) > cap:
                reply_text = reply_text[:cap] + "…"
        except Exception:
            pass
    _persist_history = (
        redis_client is not None
        and gateway_chat_history_enabled()
        and (reply_plain_for_storage or "").strip()
    )
    if _persist_history and not is_system_prompt:
        u = normalize_history_item({"role": "user", "content": message})
        a = normalize_history_item({"role": "assistant", "content": reply_plain_for_storage})
        if u and a:
            saved_items = history_for_model + [u, a]
            await redis_save_chat_history(
                redis_client,
                tenant_id,
                session_id,
                saved_items,
            )
            try:
                from core.admin_conversations import (
                    get_conversation_meta,
                    upsert_conversation_meta,
                )

                existing_conv = await get_conversation_meta(redis_client, tenant_id, session_id)
                conv_section = existing_conv.section if existing_conv else None
                await upsert_conversation_meta(
                    redis_client,
                    tenant_id=tenant_id,
                    session_id=session_id,
                    actor=(username or "").strip(),
                    section=conv_section,
                    last_worker_id=(effective_worker_id or worker_id or "").strip(),
                    user_message=message,
                    assistant_message=reply_plain_for_storage or "",
                    message_count=len(saved_items),
                )
            except Exception:
                pass
    elif _persist_history and is_system_prompt:
        from core.goals_proactive_delivery import resolve_notify_channel, should_persist_admin_history

        _notify_ch = resolve_notify_channel(payload)
        if should_persist_admin_history(_notify_ch, session_id):
            u_sys = normalize_history_item(
                {"role": "user", "content": "[Revisión proactiva /crons]"}
            )
            a_sys = normalize_history_item({"role": "assistant", "content": reply_plain_for_storage})
            if u_sys and a_sys:
                saved_items = history_for_model + [u_sys, a_sys]
                await redis_save_chat_history(
                    redis_client,
                    tenant_id,
                    session_id,
                    saved_items,
                )
                try:
                    from core.admin_conversations import (
                        get_conversation_meta,
                        upsert_conversation_meta,
                    )

                    existing_conv = await get_conversation_meta(redis_client, tenant_id, session_id)
                    conv_section = existing_conv.section if existing_conv else None
                    await upsert_conversation_meta(
                        redis_client,
                        tenant_id=tenant_id,
                        session_id=session_id,
                        actor=(username or "").strip() or "Sistema",
                        section=conv_section,
                        last_worker_id=(effective_worker_id or worker_id or "").strip(),
                        user_message="[Revisión proactiva /crons]",
                        assistant_message=reply_plain_for_storage or "",
                        message_count=len(saved_items),
                    )
                except Exception:
                    pass
    out_resp: dict[str, Any] = {
        "response": reply_plain_for_storage or "",
        "session_id": session_id,
        "worker_id": effective_worker_id or worker_id,
        "elapsed_ms": elapsed_ms,
    }
    if isinstance(usage, dict) and usage:
        out_resp["usage_tokens"] = usage
    if _telegram_response_parts_count > 1:
        out_resp["response_parts"] = _telegram_response_parts_count
    if telegram_reply_head_plain is not None and (telegram_multipart_tail_plain_for_client or "").strip():
        out_resp["telegram_reply_head_plain"] = telegram_reply_head_plain
        out_resp["telegram_multipart_tail_plain"] = telegram_multipart_tail_plain_for_client
    if (
        not is_system_prompt
        and isinstance(result, dict)
        and (result.get("sandbox_photo_base64") or "").strip()
    ):
        out_resp["sandbox_chart_delivered"] = chart_sent
    if isinstance(result, dict):
        out_resp.update(admin_visual_fields_from_invoke_result(session_id, result, tenant_id))
    clear_chat_cancel(session_id)
    return out_resp


@router.post("/api/v1/agent/chat")
@router.post("/api/v1/agent/{worker_id}/chat")
async def agent_chat(
    http_request: Request,
    worker_id: Optional[str] = None,
    body: ChatRequest | None = None,
):
    """
    Endpoint de chat multi-usuario.

    Recibe ChatRequest (message, chat_id, user_id, username, chat_type, history, stream)
    y mapea chat_id → session_id interno.
    Si el JSON no trae chat_id, se usan query params o cabeceras (ver resolve_chat_session_id).
    """
    if body is None:
        body = ChatRequest(message="", chat_id="default", user_id="system", username="system", chat_type="private")
    session_id, session_source = resolve_chat_session_id(body, http_request)
    body_tid = (body.tenant_id or "").strip() or "default"
    hdr_tid = (http_request.headers.get("X-Tenant-Id") or "").strip()
    if body_tid.lower() == "default" and hdr_tid:
        body_tid = hdr_tid
    tenant_id = effective_tenant_id(None if body_tid.lower() == "default" else body_tid)
    chat_ident = chat_identity_label(session_id, body.username)
    set_log_context(tenant_id=tenant_id, worker_id="manager", chat_id=chat_ident)
    if session_source == "default" and not (body.chat_id or "").strip():
        _gateway_log.warning(
            "[session] chat_id/session_id ausente; usando 'default' (source=%s). "
            "El estado por chat (/sandbox) no coincidirá con otros mensajes. "
            "Añade chat_id al body, ?chat_id= en la URL, o cabecera X-Chat-Id. "
            "| chat=%s",
            session_source,
            format_chat_id_for_terminal(session_id),
        )
    else:
        _gateway_log.info(
            "[session] chat_id resolved: %s (source=%s)",
            format_chat_id_for_terminal(chat_ident),
            session_source,
        )
    redis_client = getattr(http_request.app.state, "redis", None)
    _tg_mcp = getattr(http_request.app.state, "telegram_mcp", None)
    _dc_http = GatewayDeliveryContext.from_legacy_telegram(
        telegram_multipart_tail_delivery=None,
        telegram_mcp=_tg_mcp,
        telegram_forced_vault_db_path=None,
        outbound_telegram_bot_token=None,
    )
    _deliver_outbound_raw = (http_request.query_params.get("deliver_outbound") or "").strip().lower()
    _deliver_outbound = _deliver_outbound_raw in ("1", "true", "yes", "on")
    _stream = bool(body.stream) or (
        (http_request.query_params.get("stream") or "").strip().lower() in ("1", "true", "yes", "on")
    )
    _invoke_kw = {
        "redis_client": redis_client,
        "telegram_mcp": _tg_mcp,
    }
    if _stream:
        from core.sse_stream import SSE_HEADERS

        return StreamingResponse(
            invoke_chat_sse_body(
                body,
                worker_id or default_worker_id_from_env(),
                session_id,
                tenant_id,
                http_request=http_request,
                **_invoke_kw,
            ),
            media_type="text/event-stream",
            headers=dict(SSE_HEADERS),
        )
    result = await invoke_chat(
        body,
        worker_id or default_worker_id_from_env(),
        session_id=session_id,
        tenant_id=tenant_id,
        **_invoke_kw,
    )
    if _deliver_outbound:
        try:
            resp_text = (result.get("response") or "").strip() if isinstance(result, dict) else ""
            if resp_text:
                from core.goals_proactive_delivery import resolve_notify_channel, should_deliver_telegram

                _notify_deliver = resolve_notify_channel(body)
                _telegram_ok = should_deliver_telegram(_notify_deliver, session_id)
                if _telegram_ok:
                    uid_out = (body.user_id or "").strip() or session_id
                    loop = asyncio.get_running_loop()
                    _redis_url = str(settings.REDIS_URL)
                    _dc_deliver = GatewayDeliveryContext(
                        channel=_dc_http.channel,
                        telegram_multipart_tail_delivery=_dc_http.telegram_multipart_tail_delivery,
                        telegram_mcp=_dc_http.telegram_mcp,
                        telegram_forced_vault_db_path=_dc_http.telegram_forced_vault_db_path,
                        outbound_bot_token=_dc_http.outbound_bot_token,
                        prefer_native_bot_api=True,
                    )
                    await loop.run_in_executor(
                        None,
                        lambda: deliver_outbound_by_channel(
                            _dc_deliver,
                            chat_id=session_id,
                            user_id=uid_out,
                            text=resp_text,
                            worker_id=(worker_id or ""),
                            tenant_id=tenant_id,
                            redis_url=_redis_url,
                            prefer_native_bot_api=True,
                        ),
                    )
        except Exception as exc:  # noqa: BLE001
            _gateway_log.warning("agent_chat forced outbound failed: %s", exc)
    _fb = (os.getenv("DUCKCLAW_CHAT_OUTBOUND_ON_CLIENT_DISCONNECT", "true").strip().lower())
    if _fb in ("1", "true", "yes", ""):
        try:
            if await http_request.is_disconnected():
                resp_text = (result.get("response") or "").strip() if isinstance(result, dict) else ""
                if resp_text:
                    uid_fb = (body.user_id or "").strip() or session_id
                    _gateway_log.info(
                        "outbound fallback: cliente desconectado; entrega async a Telegram "
                        "(nativo o webhook) chat_id=%s len=%s",
                        format_chat_id_for_terminal(session_id),
                        len(resp_text),
                    )
                    loop = asyncio.get_running_loop()
                    _mcp_snap = _tg_mcp
                    _redis_url = str(settings.REDIS_URL)
                    _dc_fb = GatewayDeliveryContext.from_legacy_telegram(
                        telegram_multipart_tail_delivery=None,
                        telegram_mcp=_mcp_snap,
                        telegram_forced_vault_db_path=None,
                        outbound_telegram_bot_token=None,
                    )
                    await loop.run_in_executor(
                        None,
                        lambda: deliver_outbound_by_channel(
                            _dc_fb,
                            chat_id=session_id,
                            user_id=uid_fb,
                            text=resp_text,
                            worker_id=(worker_id or ""),
                            tenant_id=tenant_id,
                            redis_url=_redis_url,
                        ),
                    )
        except Exception as exc:  # noqa: BLE001
            _gateway_log.warning("outbound fallback: no se pudo comprobar/enviar: %s", exc)
    return result
