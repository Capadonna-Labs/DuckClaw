"""Ejecución del grafo LangGraph y comandos fly bajo lock de sesión."""

from __future__ import annotations

import logging
import os
import time
import traceback
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from core.chat_invoke_prepare import PreparedChatInvoke
from core.chat_locks import maybe_chat_lock_for_request
from core.fly_command_invocation import invoke_legacy_fly_command
from core.chat_visual_artifacts import persist_admin_fly_charts
from core.telegram_delivery import effective_telegram_bot_token
from duckclaw.gateway_db import resolve_env_duckdb_path
from duckclaw.utils.logger import format_chat_id_for_terminal, get_obs_logger, log_err

_gateway_log = logging.getLogger("duckclaw.gateway")
_obs_log = get_obs_logger()


async def _run_context_fold_fly_command(
    prepared: PreparedChatInvoke,
    *,
    session_id: str,
    worker_id: str,
    message: str,
    redis_client: Any,
    cmd_args: str,
    execute_with_meta_fn: Any,
) -> tuple[dict[str, Any], float]:
    """Persistencia bóveda + Redis para /summarize."""
    from duckclaw.commands.context_fold_store import save_context_fold_summary
    from duckclaw.gateway_db import GatewayDbEphemeralReadonly
    from duckclaw.graphs.conversation_traces import append_context_fold_conversation_trace
    from core.chat_history import redis_save_chat_history

    t0 = time.monotonic()
    vpath = (prepared.vault_db_path or "").strip()
    fly_db = GatewayDbEphemeralReadonly(vpath) if vpath else None
    fold_meta: dict[str, Any] = {}
    cmd_reply = ""
    try:
        if vpath:
            Path(vpath).parent.mkdir(parents=True, exist_ok=True)
        cmd_reply, fold_meta = execute_with_meta_fn(
            fly_db,
            session_id,
            cmd_args,
            tenant_id=prepared.tenant_id,
            history=prepared.history_for_model,
            vault_db_path=vpath or None,
            worker_id=worker_id,
        )
    except Exception as exc:
        _gateway_log.error(
            "context fold command failed chat=%s: %s",
            format_chat_id_for_terminal(session_id),
            exc,
        )
        cmd_reply = f"⚠️ Error al compactar: {exc}"
    vault_summary = (fold_meta.get("summary_for_vault") or "").strip()
    vault_saved = False
    if vault_summary and vpath:
        vault_saved = save_context_fold_summary(
            vpath,
            session_id,
            vault_summary,
            tenant_id=prepared.tenant_id,
        )
    kept_history = fold_meta.get("kept_history")
    if redis_client is not None and isinstance(kept_history, list) and kept_history:
        await redis_save_chat_history(
            redis_client,
            prepared.tenant_id,
            session_id,
            kept_history,
        )
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    ctx_tokens = fold_meta.get("context_estimated_tokens")
    trace_status = "SUCCESS" if not str(cmd_reply).startswith("⚠️") else "FAILED"
    try:
        append_context_fold_conversation_trace(
            session_id,
            message,
            cmd_reply,
            worker_id=worker_id,
            elapsed_ms=elapsed_ms,
            status=trace_status,
            context_estimated_tokens=int(ctx_tokens)
            if isinstance(ctx_tokens, (int, float))
            else None,
            messages_before=len(prepared.history_for_model or []),
            kept_history=kept_history if isinstance(kept_history, list) else None,
            summary_chars=len(vault_summary) if vault_summary else None,
            vault_saved=vault_saved if vault_summary else None,
        )
    except Exception:
        pass
    return (
        {
            "response": cmd_reply,
            "session_id": session_id,
            "worker_id": worker_id,
            "elapsed_ms": elapsed_ms,
            "context_estimated_tokens": int(ctx_tokens)
            if isinstance(ctx_tokens, (int, float))
            else None,
        },
        time.monotonic(),
    )


async def run_chat_graph(
    prepared: PreparedChatInvoke,
    *,
    redis_client: Any = None,
) -> tuple[dict[str, Any] | Any, float]:
    """
    Ejecuta fly command o ``ainvoke_manager_ephemeral`` bajo lock Redis.

    Returns:
        (result, t0_monotonic) — t0 al inicio del invoke del grafo.
    """
    session_id = prepared.session_id
    worker_id = prepared.worker_id
    message = prepared.message
    dc = prepared.delivery_context

    try:
        from duckclaw.graphs.graph_server import ainvoke_manager_ephemeral
    except Exception as exc:
        _gateway_log.error(
            "graph init failed chat=%s: %s\n%s",
            format_chat_id_for_terminal(session_id),
            exc,
            traceback.format_exc(),
        )
        raise HTTPException(status_code=503, detail=f"Error inicializando el grafo: {exc}") from exc

    skip_lock = prepared.skip_session_lock
    async with maybe_chat_lock_for_request(redis_client, session_id, skip_lock):
        from duckclaw.commands.fast_replies import resolve_fly_command_text

        fly_message = resolve_fly_command_text(
            user_incoming=prepared.user_incoming,
            message=message,
        )
        if fly_message.startswith("/"):
            from duckclaw.graphs.on_the_fly_commands import parse_command

            cmd_name, cmd_args = parse_command(fly_message)
            if cmd_name == "summarize":
                from duckclaw.commands.context_summarize import execute_summarize_with_meta

                return await _run_context_fold_fly_command(
                    prepared,
                    session_id=session_id,
                    worker_id=worker_id,
                    message=message,
                    redis_client=redis_client,
                    cmd_args=cmd_args,
                    execute_with_meta_fn=execute_summarize_with_meta,
                )

            fly_response = await invoke_legacy_fly_command(
                message=fly_message,
                session_id=session_id,
                worker_id=worker_id,
                tenant_id=prepared.tenant_id,
                vault_db_path=prepared.vault_db_path,
                vault_user_id=prepared.vault_user_id,
                requester_id=prepared.user_id,
                username=prepared.username,
                delivery_context=dc,
                resolve_telegram_bot_token=effective_telegram_bot_token,
                persist_admin_fly_charts=persist_admin_fly_charts,
            )
            if fly_response is not None:
                return fly_response, time.monotonic()

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
            raise HTTPException(status_code=503, detail=f"Error inicializando el grafo: {exc}") from exc

        try:
            from duckclaw.graphs.activity import set_busy

            set_busy(session_id, task=message)
        except Exception:
            pass

        # Modo /loop on: turnos agent↔user — wrap user reply when awaiting.
        graph_message = message
        if not prepared.is_system_prompt and not fly_message.startswith("/"):
            vpath = (prepared.vault_db_path or "").strip()
            if vpath:
                try:
                    from duckclaw import DuckClaw
                    from duckclaw.commands.loop import (
                        build_loop_active_user_continuation,
                        is_loop_active_mode,
                        is_loop_awaiting_user,
                        set_loop_awaiting_user,
                    )

                    vdb = DuckClaw(vpath, read_only=False, engine="python")
                    try:
                        if is_loop_active_mode(vdb, session_id) and is_loop_awaiting_user(
                            vdb, session_id
                        ):
                            graph_message = build_loop_active_user_continuation(
                                vdb,
                                session_id,
                                prepared.tenant_id,
                                prepared.user_incoming or message,
                            )
                            set_loop_awaiting_user(
                                vdb,
                                session_id,
                                False,
                                tenant_id=(prepared.tenant_id or "default"),
                            )
                    finally:
                        try:
                            vdb.close()
                        except Exception:
                            pass
                except Exception:
                    pass

        t0 = time.monotonic()
        admin_pg_vault_prev = os.environ.get("DUCKCLAW_ADMIN_PLAYGROUND_VAULT")
        if prepared.auth_policy in {"trusted_admin_console", "trusted_channel_route"}:
            admin_pg_vault = (prepared.payload_vault or prepared.vault_db_path or "").strip()
            if admin_pg_vault:
                os.environ["DUCKCLAW_ADMIN_PLAYGROUND_VAULT"] = resolve_env_duckdb_path(admin_pg_vault)
            else:
                os.environ.pop("DUCKCLAW_ADMIN_PLAYGROUND_VAULT", None)
        try:
            from duckclaw.graphs.chat_cancel import ChatCancelledError

            try:
                result = await ainvoke_manager_ephemeral(
                    graph_message,
                    prepared.history_for_graph,
                    session_id,
                    tenant_id=prepared.tenant_id,
                    user_id=prepared.vault_user_id,
                    username=prepared.username,
                    user_incoming=getattr(prepared.payload, "graph_user_incoming", None)
                    or prepared.user_incoming,
                    vault_db_path=prepared.vault_db_path,
                    shared_db_path=prepared.shared_db_path,
                    is_system_prompt=prepared.is_system_prompt
                    or graph_message.strip().startswith("[SYSTEM_EVENT:"),
                    outbound_telegram_bot_token=(dc.outbound_bot_token or "").strip() or None,
                    entry_worker_id=(worker_id or "").strip() or None,
                    integration_channel=(dc.channel or "").strip() or None,
                    project_id=(getattr(prepared.payload, "project_id", None) or "").strip() or None,
                    knowledge_scope=(getattr(prepared.payload, "knowledge_scope", None) or "").strip() or None,
                )
            except ChatCancelledError:
                try:
                    from duckclaw.graphs.activity import set_idle

                    set_idle(session_id)
                except Exception:
                    pass
                elapsed_cancel = int((time.monotonic() - t0) * 1000)
                return (
                    {
                        "response": "Interrumpido.",
                        "session_id": session_id,
                        "worker_id": worker_id,
                        "elapsed_ms": elapsed_cancel,
                        "interrupted": True,
                    },
                    t0,
                )
            except Exception as exc:
                try:
                    from duckclaw.graphs.activity import set_idle

                    set_idle(session_id)
                except Exception:
                    pass
                elapsed_fail = int((time.monotonic() - t0) * 1000)
                try:
                    from duckclaw.graphs.on_the_fly_commands import append_task_audit, get_worker_id_for_chat
                    from duckclaw.graphs.graph_server import get_db

                    db = get_db()
                    wid = get_worker_id_for_chat(db, session_id) or worker_id
                    append_task_audit(db, session_id, wid, message, "FAILED", elapsed_fail)
                except Exception:
                    pass
                try:
                    if os.environ.get("DUCKCLAW_SAVE_CONVERSATION_TRACES", "true").strip().lower() in (
                        "true",
                        "1",
                        "yes",
                    ):
                        from duckclaw.graphs.conversation_traces import append_conversation_trace
                        from duckclaw.graphs.on_the_fly_commands import get_effective_system_prompt
                        from duckclaw.graphs.graph_server import get_db

                        db = get_db()
                        sys_prompt = (get_effective_system_prompt(db, worker_id) or "").strip()
                        sys_prompt = sys_prompt or (os.environ.get("DUCKCLAW_SYSTEM_PROMPT") or "").strip() or None
                        append_conversation_trace(
                            session_id,
                            message,
                            str(exc)[:8192],
                            worker_id=worker_id,
                            elapsed_ms=elapsed_fail,
                            status="FAILED",
                            system_prompt=sys_prompt,
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
                raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            if admin_pg_vault_prev is None:
                os.environ.pop("DUCKCLAW_ADMIN_PLAYGROUND_VAULT", None)
            else:
                os.environ["DUCKCLAW_ADMIN_PLAYGROUND_VAULT"] = admin_pg_vault_prev

        try:
            from duckclaw.graphs.activity import set_idle

            set_idle(session_id)
        except Exception:
            pass

    return result, t0
