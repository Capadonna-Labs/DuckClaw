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
    fold_ok = bool(vault_summary) and not str(cmd_reply).startswith("⚠️")
    compacted_history = (
        [item for item in kept_history if isinstance(item, dict)]
        if fold_ok and isinstance(kept_history, list)
        else None
    )
    # Escribe la base compacta ya; finalize añadirá el turno /summarize
    # usando compacted_history (no history_for_model gordo).
    if redis_client is not None and compacted_history is not None:
        await redis_save_chat_history(
            redis_client,
            prepared.tenant_id,
            session_id,
            compacted_history,
        )
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    ctx_tokens = fold_meta.get("context_estimated_tokens")
    trace_status = "SUCCESS" if fold_ok else "FAILED"
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
            kept_history=compacted_history,
            summary_chars=len(vault_summary) if vault_summary else None,
            vault_saved=vault_saved if vault_summary else None,
        )
    except Exception:
        pass
    result_payload: dict[str, Any] = {
        "response": cmd_reply,
        "session_id": session_id,
        "worker_id": worker_id,
        "elapsed_ms": elapsed_ms,
        "context_estimated_tokens": int(ctx_tokens)
        if isinstance(ctx_tokens, (int, float))
        else None,
    }
    if compacted_history is not None:
        # Evita que finalize re-infle Redis con prepared.history_for_model.
        result_payload["compacted_history"] = compacted_history
    return (result_payload, time.monotonic())


async def _auto_compact_history_if_needed(
    prepared: PreparedChatInvoke,
    *,
    redis_client: Any,
) -> tuple[PreparedChatInvoke, list[dict[str, Any]] | None, str]:
    """
    Pre-turn: if the history reached ~97% of its token budget, summarize the old
    turns (same LLM fold as /summarize) and keep the recent tail, instead of the
    old silent sliding window. Falls back to trimming the oldest turns when there's
    no vault to hold the summary. Returns (prepared, compacted_history, summary).
    """
    import asyncio
    from dataclasses import replace

    from core.chat_history import (
        chat_history_token_budget,
        history_estimated_tokens,
        history_needs_compaction,
        redis_save_chat_history,
        trim_history_to_budget,
    )

    history = list(prepared.history_for_model or [])
    if prepared.is_system_prompt or not history_needs_compaction(history):
        return prepared, None, ""

    session_id = prepared.session_id
    before = history_estimated_tokens(history)
    try:
        from duckclaw.graphs.chat_heartbeat import publish_admin_chat_heartbeat

        publish_admin_chat_heartbeat(
            session_id,
            f"🗜️ Compactando contexto ({before:,} de {chat_history_token_budget():,} tokens)…",
            kind="status",
        )
    except Exception:
        pass

    summary = ""
    compacted: list[dict[str, Any]] | None = None
    vpath = (prepared.vault_db_path or "").strip()
    if vpath:
        from duckclaw.commands.context_fold_store import save_context_fold_summary
        from duckclaw.commands.context_summarize import run_manual_context_fold
        from duckclaw.gateway_db import GatewayDbEphemeralReadonly

        def _fold() -> tuple[str | None, str | None, dict[str, Any]]:
            return run_manual_context_fold(
                GatewayDbEphemeralReadonly(vpath),
                session_id,
                tenant_id=prepared.tenant_id,
                worker_id=prepared.worker_id,
                history=history,
                vault_db_path=vpath,
            )

        try:
            fold_summary, err, meta = await asyncio.to_thread(_fold)
        except Exception as exc:
            fold_summary, err, meta = None, str(exc), {}
        kept = meta.get("kept_history") if isinstance(meta, dict) else None
        if fold_summary and not err and isinstance(kept, list):
            summary = fold_summary.strip()
            save_context_fold_summary(vpath, session_id, summary, tenant_id=prepared.tenant_id)
            compacted = [item for item in kept if isinstance(item, dict)]
        else:
            _gateway_log.warning(
                "auto-compaction fold failed chat=%s, trimming instead: %s",
                format_chat_id_for_terminal(session_id),
                err,
            )
    if compacted is None:
        compacted = trim_history_to_budget(history)

    if redis_client is not None:
        await redis_save_chat_history(redis_client, prepared.tenant_id, session_id, compacted)
    _gateway_log.info(
        "auto-compaction chat=%s history %d→%d tokens (%d→%d msgs, summary=%s)",
        format_chat_id_for_terminal(session_id),
        before,
        history_estimated_tokens(compacted),
        len(history),
        len(compacted),
        "yes" if summary else "no",
    )
    new_prepared = replace(
        prepared,
        history_for_model=compacted,
        # Document turns deliberately send no history to the graph; keep that.
        history_for_graph=compacted if prepared.history_for_graph else [],
    )
    return new_prepared, compacted, summary


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
            from duckclaw.commands.fly_dispatch import is_human_only_fly_command

            if prepared.is_system_prompt and is_human_only_fly_command(cmd_name):
                _gateway_log.warning(
                    "blocked human-only fly command in system turn chat=%s cmd=/%s",
                    format_chat_id_for_terminal(session_id),
                    cmd_name,
                )
                return {
                    "response": f"/{cmd_name} solo lo puede ejecutar una persona, no un turno automático.",
                    "session_id": session_id,
                    "worker_id": worker_id,
                    "elapsed_ms": 0,
                }, time.monotonic()
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

                    vdb = DuckClaw(vpath, read_only=True, engine="python")
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
                            # Clear awaiting flag via typed command (no long-lived RW vault handle).
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

        prepared, auto_compacted, auto_summary = await _auto_compact_history_if_needed(
            prepared, redis_client=redis_client
        )

        t0 = time.monotonic()
        admin_pg_vault_prev = os.environ.get("DUCKCLAW_ADMIN_PLAYGROUND_VAULT")
        from core.chat_history import compute_turn_user_index, redis_load_chat_history

        index_history = prepared.history_for_model
        if prepared.is_system_prompt and not index_history:
            # Loop/cron turns run without history, yet persist append to the stored
            # one; without it every loop tool box landed under the chat's 1st message.
            try:
                index_history = await redis_load_chat_history(
                    redis_client, prepared.tenant_id, session_id
                )
            except Exception:
                index_history = []
        turn_user_index = compute_turn_user_index(index_history)
        heartbeat_turn_token = None
        try:
            from duckclaw.graphs.chat_heartbeat import (
                set_admin_chat_turn_user_index,
                set_admin_turn_user_index,
            )

            heartbeat_turn_token = set_admin_turn_user_index(turn_user_index)
            set_admin_chat_turn_user_index(session_id, turn_user_index)
        except Exception:
            heartbeat_turn_token = None
        from core.admin_chat_heartbeat import reset_admin_heartbeat_backlog

        await reset_admin_heartbeat_backlog(redis_client, session_id)
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
                    analytical_summary=auto_summary or None,
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
            if heartbeat_turn_token is not None:
                try:
                    from duckclaw.graphs.chat_heartbeat import (
                        clear_admin_chat_turn_user_index,
                        reset_admin_turn_user_index,
                    )

                    reset_admin_turn_user_index(heartbeat_turn_token)
                    clear_admin_chat_turn_user_index(session_id)
                except Exception:
                    pass
            if admin_pg_vault_prev is None:
                os.environ.pop("DUCKCLAW_ADMIN_PLAYGROUND_VAULT", None)
            else:
                os.environ["DUCKCLAW_ADMIN_PLAYGROUND_VAULT"] = admin_pg_vault_prev

        try:
            from duckclaw.graphs.activity import set_idle

            set_idle(session_id)
        except Exception:
            pass

        if isinstance(result, dict):
            from core.chat_history import chat_history_token_budget

            if auto_compacted is not None:
                # finalize persists this base (+ this turn) instead of the pre-compaction history.
                result["compacted_history"] = auto_compacted
            breakdown = result.get("context_token_breakdown")
            if isinstance(breakdown, dict):
                breakdown["budget"] = chat_history_token_budget()

    return result, t0
