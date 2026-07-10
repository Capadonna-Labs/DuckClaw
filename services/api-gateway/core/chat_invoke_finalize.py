"""Post-procesado de respuesta del grafo: formato, charts, historial Redis, payload HTTP."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any

from core.chat_history_persist import persist_chat_history
from core.chat_invoke_prepare import PreparedChatInvoke
from core.chat_reply_format import (
    beautify_structured_insight_telegram,
    clean_agent_response,
    strip_false_chart_delivery_lines,
    strip_markdown_bold,
    truncate_log,
)
from core.chat_visual_artifacts import admin_visual_fields_from_invoke_result
from core.sandbox_figure_b64 import decode_sandbox_figure_base64, decode_valid_sandbox_image_bytes
from core.telegram_chunking import (
    TELEGRAM_SENDMESSAGE_CHAR_LIMIT,
    plain_subchunks_for_telegram_budget,
    split_plain_text_for_telegram_reply,
    telegram_reply_plain_chunk_size,
)
from core.telegram_delivery import (
    effective_telegram_bot_token,
    strip_lines_mentioning_workspace_output,
)
from core.telegram_media_upload import send_sandbox_chart_to_telegram_sync
from duckclaw.utils.logger import format_chat_id_for_terminal, get_obs_logger, log_res, set_log_context
from duckclaw.utils.telegram_markdown_v2 import (
    llm_markdown_to_telegram_html,
    unescape_telegram_markdown_v2_layers,
)

_gateway_log = logging.getLogger("duckclaw.gateway")
_obs_log = get_obs_logger()


def _is_loop_footer_turn(
    *,
    user_incoming: str,
    message: str,
    fly_cmd: str,
    cmd_name: str,
) -> bool:
    """True si el turno es /loop o ciclo auto-mejora (SYSTEM_EVENT), no solo fly /command."""
    try:
        from duckclaw.commands.loop import is_loop_status_fly_text

        if is_loop_status_fly_text(user_incoming, fly_cmd, message):
            return False
    except Exception:
        pass
    if cmd_name in ("loop", "meditate"):
        return True
    try:
        from duckclaw.commands.loop import LOOP_SYSTEM_USER_LABEL

        label = (LOOP_SYSTEM_USER_LABEL or "").strip()
    except Exception:
        label = "[Ciclo loop]"
    for chunk in (user_incoming, fly_cmd, message):
        c = chunk or ""
        if label and label in c:
            return True
        if "Modo /loop activo" in c:
            return True
    low = (message or "").lower()
    if "[system_event:" in low and any(
        tok in low
        for tok in ("meditate", "homeostasis", "validación hitl", "validacion hitl")
    ):
        return True
    return False


def _reply_already_has_loop_schedule_footer(text: str) -> bool:
    """Evita duplicar pie de próximo ciclo; no bloquea fly ack con 'Modo /loop --delta'."""
    t = text or ""
    markers = (
        "⏭️ **Próximo ciclo",
        "⏭️ **Modo /loop:** inactivo",
        "⏭️ **Modo /loop activo** — esperando",
        "⏭️ **Modo /loop activo** — ciclo en curso",
        "⏭️ **Modo /loop --delta:**",
        "Próximo ciclo /loop --delta",
        "Próximo ciclo auto-mejora",
        "silencio ~",
    )
    return any(m in t for m in markers)


def _loop_footer_chat_id(prepared: PreparedChatInvoke) -> str:
    raw = (getattr(prepared.payload, "chat_id", None) or "").strip() or prepared.session_id
    try:
        from duckclaw.commands.loop import _normalize_admin_chat_id

        return _normalize_admin_chat_id(raw)
    except Exception:
        return raw


async def finalize_chat_response(
    prepared: PreparedChatInvoke,
    result: dict[str, Any] | Any,
    *,
    t0: float,
    redis_client: Any = None,
) -> dict[str, Any]:
    """Transforma el resultado crudo del grafo en el dict de respuesta HTTP/Telegram."""
    session_id = prepared.session_id
    worker_id = prepared.worker_id
    message = prepared.message
    tenant_id = prepared.tenant_id
    dc = prepared.delivery_context
    is_system_prompt = prepared.is_system_prompt
    history_for_model = prepared.history_for_model
    username = prepared.username
    chat_ident = prepared.chat_ident

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
        from duckclaw.workers.reddit_formatters import format_reddit_mcp_reply_if_applicable

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

    try:
        from duckclaw.commands.fast_replies import resolve_fly_command_text
        from duckclaw.graphs.on_the_fly_commands import parse_command

        fly_cmd = resolve_fly_command_text(
            user_incoming=prepared.user_incoming,
            message=prepared.message,
        )
        cmd_name, _cmd_args = parse_command(fly_cmd)
        if _is_loop_footer_turn(
            user_incoming=prepared.user_incoming,
            message=prepared.message,
            fly_cmd=fly_cmd,
            cmd_name=cmd_name,
        ):
            vpath = (prepared.vault_db_path or "").strip()
            if vpath:
                from duckclaw import DuckClaw
                from duckclaw.commands.loop import format_loop_next_tick_footer

                vdb = DuckClaw(vpath, read_only=True, engine="python")
                try:
                    footer = format_loop_next_tick_footer(
                        vdb, _loop_footer_chat_id(prepared)
                    )
                    if footer and not _reply_already_has_loop_schedule_footer(reply_text or ""):
                        reply_text = (reply_text or "") + footer
                    # Tras respuesta del agente en modo activo: esperar turno usuario.
                    try:
                        from duckclaw.commands.loop import (
                            is_loop_active_mode,
                            set_loop_awaiting_user,
                        )

                        if is_loop_active_mode(vdb, _loop_footer_chat_id(prepared)):
                            # Reabrir write-capable para marcar awaiting (misma vault).
                            vdb.close()
                            vdb_w = DuckClaw(vpath, read_only=False, engine="python")
                            try:
                                set_loop_awaiting_user(
                                    vdb_w,
                                    _loop_footer_chat_id(prepared),
                                    True,
                                    tenant_id=(prepared.tenant_id or "default"),
                                )
                            finally:
                                try:
                                    vdb_w.close()
                                except Exception:
                                    pass
                            vdb = None  # already closed
                    except Exception:
                        pass
                finally:
                    if vdb is not None:
                        try:
                            vdb.close()
                        except Exception:
                            pass
            elif not vpath:
                pass
            # Fallback: system meditate cycle without vault footer path still marks awaiting via hub? skip.
    except Exception:
        pass

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

    chart_sent = await _maybe_deliver_sandbox_chart(
        prepared=prepared,
        result=result,
        reply_plain_for_storage=reply_plain_for_storage,
    )
    if chart_sent:
        reply_plain_for_storage = strip_lines_mentioning_workspace_output(reply_plain_for_storage or "")

    _append_success_audit(
        prepared,
        result,
        effective_worker_id,
        elapsed_ms,
        message,
        reply_plain_for_storage,
    )
    telegram_parts = _split_telegram_multipart(reply_plain_for_storage)
    await persist_chat_history(
        prepared=prepared,
        redis_client=redis_client,
        reply_plain_for_storage=reply_plain_for_storage,
        effective_worker_id=effective_worker_id,
        history_for_model=history_for_model,
        message=message,
        username=username,
    )

    if is_system_prompt and (reply_plain_for_storage or "").strip():
        try:
            from core.goals_proactive_delivery import resolve_notify_channel, should_persist_admin_history
            from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session, publish_admin_chat_heartbeat

            notify_ch = resolve_notify_channel(prepared.payload)
            if should_persist_admin_history(notify_ch, session_id) and is_admin_ui_chat_session(session_id):
                publish_admin_chat_heartbeat(
                    session_id,
                    (reply_plain_for_storage or "").strip(),
                    kind="status",
                    worker_id=(effective_worker_id or worker_id or "").strip() or None,
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
    if telegram_parts["parts_count"] > 1:
        out_resp["response_parts"] = telegram_parts["parts_count"]
    if telegram_parts["head"] is not None and (telegram_parts["tail"] or "").strip():
        out_resp["telegram_reply_head_plain"] = telegram_parts["head"]
        out_resp["telegram_multipart_tail_plain"] = telegram_parts["tail"]
    if (
        not is_system_prompt
        and isinstance(result, dict)
        and (result.get("sandbox_photo_base64") or "").strip()
    ):
        out_resp["sandbox_chart_delivered"] = chart_sent
    if isinstance(result, dict):
        out_resp.update(admin_visual_fields_from_invoke_result(session_id, result, tenant_id))

    from duckclaw.graphs.chat_cancel import clear_chat_cancel

    clear_chat_cancel(session_id)
    return out_resp


async def _maybe_deliver_sandbox_chart(
    *,
    prepared: PreparedChatInvoke,
    result: dict[str, Any] | Any,
    reply_plain_for_storage: str,
) -> bool:
    del reply_plain_for_storage
    if prepared.is_system_prompt or not isinstance(result, dict):
        return False
    photo_b64 = (result.get("sandbox_photo_base64") or "").strip()
    if not photo_b64:
        return False
    png_bytes = decode_valid_sandbox_image_bytes(photo_b64)
    if not png_bytes:
        raw_try = decode_sandbox_figure_base64(photo_b64)
        _gateway_log.warning(
            "sandbox chart: base64 no produce PNG/JPEG válido (b64_len=%s, decoded_len=%s, mod4=%s)",
            len(photo_b64),
            len(raw_try),
            len("".join(photo_b64.split())) % 4,
        )
    dc = prepared.delivery_context
    if not png_bytes or (dc.channel or "telegram").strip().lower() != "telegram":
        return False
    token = (dc.outbound_bot_token or "").strip() or effective_telegram_bot_token()
    if not token:
        _gateway_log.warning(
            "sandbox chart: hay PNG del sandbox pero no hay token de salida para este request "
            "(outbound_bot_token ni token efectivo del contexto)."
        )
        return False
    loop = asyncio.get_running_loop()
    return bool(
        await loop.run_in_executor(
            None,
            lambda: send_sandbox_chart_to_telegram_sync(
                bot_token=token,
                chat_id=str(prepared.session_id),
                image_bytes=png_bytes,
            ),
        )
    )


def _append_success_audit(
    prepared: PreparedChatInvoke,
    result: dict[str, Any] | Any,
    effective_worker_id: str,
    elapsed_ms: int,
    message: str,
    reply_plain_for_storage: str,
) -> None:
    if isinstance(result, dict) and not result.get("_audit_done"):
        try:
            from duckclaw.graphs.on_the_fly_commands import append_task_audit, get_worker_id_for_chat
            from duckclaw.graphs.graph_server import get_db

            db = get_db()
            wid = get_worker_id_for_chat(db, prepared.session_id) or prepared.worker_id
            plan_title = result.get("plan_title")
            append_task_audit(db, prepared.session_id, wid, message, "SUCCESS", elapsed_ms, plan_title=plan_title)
        except Exception:
            pass
    _append_success_conversation_trace(
        prepared,
        result,
        effective_worker_id,
        elapsed_ms,
        message,
        reply_plain_for_storage,
    )


def _append_success_conversation_trace(
    prepared: PreparedChatInvoke,
    result: dict[str, Any] | Any,
    effective_worker_id: str,
    elapsed_ms: int,
    message: str,
    reply_plain_for_storage: str,
) -> None:
    """Persist SFT trace even when manager already wrote task_audit (_audit_done)."""
    if not isinstance(result, dict):
        return
    try:
        if os.environ.get("DUCKCLAW_SAVE_CONVERSATION_TRACES", "true").strip().lower() not in (
            "true",
            "1",
            "yes",
        ):
            return
        from duckclaw.graphs.conversation_traces import append_conversation_trace
        from duckclaw.graphs.on_the_fly_commands import get_effective_system_prompt
        from duckclaw.graphs.graph_server import get_db

        trace_messages = result.get("messages")
        db = get_db()
        system_from_prompt = (get_effective_system_prompt(db, effective_worker_id) or "").strip()
        system_for_trace = system_from_prompt or (os.environ.get("DUCKCLAW_SYSTEM_PROMPT") or "").strip() or None
        append_conversation_trace(
            prepared.session_id,
            message,
            reply_plain_for_storage or "",
            worker_id=effective_worker_id,
            elapsed_ms=elapsed_ms,
            status="SUCCESS",
            system_prompt=system_for_trace,
            messages=trace_messages,
        )
    except Exception:
        pass


def _split_telegram_multipart(reply_plain_for_storage: str) -> dict[str, Any]:
    parts_count = 1
    head: str | None = None
    tail: str | None = None
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
        parts_count = len(plain_parts)
        tail_plain = "\n\n".join(plain_parts[1:]) if len(plain_parts) > 1 else ""
        if tail_plain.strip():
            head = plain_parts[0]
            tail = tail_plain
    except Exception:
        pass
    return {"parts_count": parts_count, "head": head, "tail": tail}
