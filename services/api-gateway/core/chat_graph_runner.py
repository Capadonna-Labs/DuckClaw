"""Ejecución del grafo LangGraph y comandos fly bajo lock de sesión."""

from __future__ import annotations

import logging
import os
import time
import traceback
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
        if message.startswith("/"):
            fly_response = await invoke_legacy_fly_command(
                message=message,
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
                    message,
                    prepared.history_for_model,
                    session_id,
                    tenant_id=prepared.tenant_id,
                    user_id=prepared.vault_user_id,
                    username=prepared.username,
                    user_incoming=prepared.user_incoming,
                    vault_db_path=prepared.vault_db_path,
                    shared_db_path=prepared.shared_db_path,
                    is_system_prompt=prepared.is_system_prompt,
                    outbound_telegram_bot_token=(dc.outbound_bot_token or "").strip() or None,
                    entry_worker_id=(worker_id or "").strip() or None,
                    integration_channel=(dc.channel or "").strip() or None,
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
