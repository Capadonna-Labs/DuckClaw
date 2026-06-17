"""Sandbox heartbeat and noVNC pre-DM scheduling for worker tools."""

from __future__ import annotations

import logging
import os
import time

from duckclaw.integrations.telegram import effective_telegram_bot_token_outbound
from duckclaw.workers.manifest import WorkerSpec
from duckclaw.workers.provider_input_budget import normalized_context_pruning as _normalized_context_pruning

_log = logging.getLogger(__name__)


def _sandbox_heartbeat_allowed(spec: WorkerSpec) -> bool:
    cp = _normalized_context_pruning(spec)
    if not cp.get("sandbox_heartbeat"):
        return False
    v = (os.getenv("DUCKCLAW_SANDBOX_HEARTBEAT", "true").strip().lower())
    if v in ("0", "false", "no", "off"):
        return False
    return bool(effective_telegram_bot_token_outbound())


def _heartbeat_elapsed_sec(state: dict) -> float | None:
    t0 = state.get("subagent_turn_started_monotonic")
    if not isinstance(t0, (int, float)):
        return None
    return max(0.0, time.monotonic() - float(t0))


def _send_sandbox_heartbeat_telegram(state: dict) -> None:
    from duckclaw.graphs.chat_heartbeat import (
        format_tool_heartbeat,
        is_admin_ui_chat_session,
        normalize_telegram_chat_id_for_outbound,
    )

    cid_raw = str(state.get("chat_id") or state.get("session_id") or "").strip()
    if is_admin_ui_chat_session(cid_raw):
        return
    cid = normalize_telegram_chat_id_for_outbound(cid_raw) or cid_raw
    uid = str(state.get("user_id") or "").strip() or cid
    if not cid:
        return
    _hb = (state.get("subagent_instance_label") or "").strip() or None
    _pt = (state.get("heartbeat_plan_title") or "").strip() or None
    text = format_tool_heartbeat(
        _hb,
        "📊 Estoy procesando los datos y generando tus gráficos. "
        "Esto puede tomar unos segundos...",
        plan_title=_pt,
        elapsed_sec=_heartbeat_elapsed_sec(state),
    )
    token = effective_telegram_bot_token_outbound()
    if token:
        try:
            from duckclaw.integrations.telegram.telegram_outbound_sync import (
                send_long_plain_text_markdown_v2_chunks_sync,
            )

            n = send_long_plain_text_markdown_v2_chunks_sync(
                bot_token=token,
                chat_id=cid,
                plain_text=text,
                log=_log,
            )
            if n > 0:
                _log.info("sandbox heartbeat: nativo OK chat_id=%r", cid)
                return
        except Exception as exc:
            _log.debug("sandbox heartbeat nativo falló: %s", exc)
    _log.debug("sandbox heartbeat: sin token Bot API para chat_id=%r", cid)


def _novnc_pre_dm_always_enabled() -> bool:
    v = (os.getenv("DUCKCLAW_BROWSER_NOVNC_PRE_DM") or "").strip().lower()
    return v in ("1", "true", "yes", "on", "always")


def _send_novnc_pre_dm_fallback(
    state: dict,
    vnc_url: str,
    *,
    routing_worker_id: str,
    novnc_session_id: str = "",
) -> None:
    """DM corto con enlace si heartbeat de chat está off y ``DUCKCLAW_BROWSER_NOVNC_PRE_DM=always``."""
    import threading

    from duckclaw.graphs.chat_heartbeat import (
        _resolve_heartbeat_outbound_bot_token,
        normalize_telegram_chat_id_for_outbound,
    )
    from duckclaw.graphs import novnc_registry as nr  # noqa: PLC0415
    from duckclaw.integrations.telegram.telegram_outbound_sync import (
        send_long_plain_text_markdown_v2_chunks_sync,
    )

    cid_raw = str(state.get("chat_id") or state.get("session_id") or "").strip()
    cid = normalize_telegram_chat_id_for_outbound(cid_raw) or cid_raw
    if not cid or not vnc_url:
        return
    _ns = (novnc_session_id or "").strip()
    if _ns and not nr.consume_initial_vnc_telegram_link(_ns):
        return
    tok_ex = (state.get("outbound_telegram_bot_token") or "").strip() or None
    token = _resolve_heartbeat_outbound_bot_token(
        tok_ex,
        (routing_worker_id or "").strip() or None,
    )
    if not token:
        _log.debug("novnc pre-dm: sin token Bot API")
        return
    plain = (
        "🖥️ NoVNC (sandbox browser)\n\n"
        f"{vnc_url}\n\n"
        "🌐 El agente ejecutará la automatización en el sandbox."
    )

    def _run() -> None:
        try:
            n = send_long_plain_text_markdown_v2_chunks_sync(
                bot_token=token,
                chat_id=cid,
                plain_text=plain,
                log=_log,
            )
            if n > 0:
                _log.info("novnc pre-dm fallback: nativo OK chat_id=%r", cid)
        except Exception as exc:
            _log.debug("novnc pre-dm fallback failed: %s", exc)

    threading.Thread(target=_run, name="duckclaw-novnc-pre-dm", daemon=True).start()


def _schedule_run_browser_novnc_tool_heartbeat(
    state: dict,
    *,
    routing_worker_id: str,
    vnc_url: str | None,
    novnc_session_id: str = "",
) -> None:
    from duckclaw.graphs import novnc_registry as nr  # noqa: PLC0415
    from duckclaw.graphs.chat_heartbeat import (
        format_tool_heartbeat,
        heartbeat_message_for_tool,
        is_admin_ui_chat_session,
        is_chat_heartbeat_enabled,
        schedule_chat_heartbeat_dm,
    )

    _hcid = str(state.get("chat_id") or state.get("session_id") or "").strip()
    if is_admin_ui_chat_session(_hcid):
        # Admin SSE: publish_admin_tool_event (vía _schedule_tool_heartbeat) ya cubre start/done.
        return

    _hb_head = (state.get("subagent_instance_label") or "").strip() or None
    _hb_uname = (state.get("username") or "").strip() or None
    _hb_plan = (state.get("heartbeat_plan_title") or "").strip() or None
    _hb_tok = (state.get("outbound_telegram_bot_token") or "").strip() or None
    _htid = (state.get("tenant_id") or "default").strip() or "default"
    _huid = str(state.get("user_id") or "").strip() or _hcid

    _ns = (novnc_session_id or "").strip()
    _hb_on = is_chat_heartbeat_enabled(_htid, _hcid)

    if vnc_url:
        if _hb_on:
            _include_link = nr.consume_initial_vnc_telegram_link(_ns) if _ns else True
            if _include_link:
                body = (
                    "🖥️ Enlace noVNC (pantalla del navegador en vivo):\n"
                    f"{vnc_url}\n\n"
                    "🌐 El agente ejecutará ahora la automatización en el sandbox; puedes seguirla en este enlace."
                )
            else:
                body = (
                    "🌐 Automatización del sandbox en curso. "
                    "El enlace noVNC ya se envió al inicio de esta sesión; si lo necesitas otra vez, "
                    "pide «enlace noVNC» o usa la herramienta get_browser_session_url."
                )
        else:
            body = heartbeat_message_for_tool("run_browser_sandbox")
    else:
        body = heartbeat_message_for_tool("run_browser_sandbox")

    _elapsed = _heartbeat_elapsed_sec(state)
    text = format_tool_heartbeat(
        _hb_head,
        body,
        plan_title=_hb_plan,
        elapsed_sec=_elapsed,
    )

    if _hb_on:
        schedule_chat_heartbeat_dm(
            _htid,
            _hcid,
            _huid,
            text,
            log_worker_id=_hb_head,
            log_username=_hb_uname,
            log_plan_title=_hb_plan,
            outbound_bot_token=_hb_tok,
            routing_worker_id=routing_worker_id,
        )
    elif vnc_url and _novnc_pre_dm_always_enabled():
        _send_novnc_pre_dm_fallback(
            state,
            vnc_url,
            routing_worker_id=routing_worker_id,
            novnc_session_id=_ns,
        )
