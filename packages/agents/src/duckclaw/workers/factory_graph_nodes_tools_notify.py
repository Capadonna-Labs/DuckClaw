"""Admin UI tool-phase notifications for the worker tools node."""

from __future__ import annotations

from typing import Any


def notify_admin_tool_phase(
    *,
    state: dict[str, Any],
    tool_name: str,
    phase: str,
    detail: str = "",
    elapsed_ms: float | None = None,
    worker_id: str,
    heartbeat_head: str | None = None,
) -> None:
    chat_id = str(state.get("chat_id") or state.get("session_id") or "").strip()
    if not chat_id:
        return
    try:
        from duckclaw.graphs.chat_heartbeat import (
            is_admin_ui_chat_session,
            publish_admin_tool_event,
        )

        if not is_admin_ui_chat_session(chat_id):
            return
        publish_admin_tool_event(
            chat_id,
            tool_name,
            phase,
            worker_id=(heartbeat_head or worker_id or "").strip() or None,
            detail=detail,
            elapsed_ms=elapsed_ms,
        )
    except Exception:
        pass


def schedule_tool_heartbeat_or_admin_start(
    *,
    state: dict[str, Any],
    tool_name: str,
    worker_id: str,
    heartbeat_head: str | None,
    heartbeat_username: str | None,
    heartbeat_plan: str | None,
    heartbeat_token: str | None,
) -> None:
    tenant_id = (state.get("tenant_id") or "default").strip() or "default"
    chat_id = str(state.get("chat_id") or state.get("session_id") or "").strip()
    user_id = str(state.get("user_id") or "").strip() or chat_id
    try:
        from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

        admin_ui = is_admin_ui_chat_session(chat_id)
    except Exception:
        admin_ui = False
    if admin_ui:
        notify_admin_tool_phase(
            state=state,
            tool_name=tool_name,
            phase="start",
            worker_id=worker_id,
            heartbeat_head=heartbeat_head,
        )
        return
    from duckclaw.graphs.chat_heartbeat import (
        format_tool_heartbeat,
        heartbeat_message_for_tool,
        schedule_chat_heartbeat_dm,
    )
    from duckclaw.workers.factory_sandbox_notify import _heartbeat_elapsed_sec

    schedule_chat_heartbeat_dm(
        tenant_id,
        chat_id,
        user_id,
        format_tool_heartbeat(
            heartbeat_head,
            heartbeat_message_for_tool(tool_name),
            plan_title=heartbeat_plan,
            elapsed_sec=_heartbeat_elapsed_sec(state),
        ),
        log_worker_id=heartbeat_head,
        log_username=heartbeat_username,
        log_plan_title=heartbeat_plan,
        outbound_bot_token=heartbeat_token,
        routing_worker_id=worker_id,
    )
