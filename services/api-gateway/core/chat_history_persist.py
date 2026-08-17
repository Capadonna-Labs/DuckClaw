"""Persistencia de historial Redis y metadatos de conversación tras un turno chat."""

from __future__ import annotations

from typing import Any

from core.chat_history import (
    gateway_chat_history_enabled,
    normalize_history_item,
    redis_save_chat_history,
)
from core.chat_invoke_prepare import PreparedChatInvoke


async def persist_chat_history(
    *,
    prepared: PreparedChatInvoke,
    redis_client: Any,
    reply_plain_for_storage: str,
    effective_worker_id: str,
    history_for_model: list[dict[str, Any]],
    message: str,
    username: str,
) -> None:
    if not gateway_chat_history_enabled() or not (reply_plain_for_storage or "").strip():
        return
    tenant_id = prepared.tenant_id
    session_id = prepared.session_id
    try:
        from duckclaw.graphs.chat_heartbeat import admin_report_chat_id, is_admin_ui_chat_session

        if is_admin_ui_chat_session(session_id):
            session_id = admin_report_chat_id(session_id) or session_id
    except Exception:
        pass
    if not prepared.is_system_prompt:
        user_for_history = (prepared.user_incoming or message or "").strip()
        user_item = normalize_history_item({"role": "user", "content": user_for_history})
        assistant_item = normalize_history_item({"role": "assistant", "content": reply_plain_for_storage})
        if not user_item or not assistant_item:
            return
        saved_items = history_for_model + [user_item, assistant_item]
        await redis_save_chat_history(redis_client, tenant_id, session_id, saved_items)
        await upsert_conversation_meta(
            redis_client,
            tenant_id=tenant_id,
            session_id=session_id,
            actor=(username or "").strip(),
            effective_worker_id=effective_worker_id,
            worker_id=prepared.worker_id,
            user_message=user_for_history,
            assistant_message=reply_plain_for_storage,
            message_count=len(saved_items),
        )
        await _touch_loop_activity_if_configured(prepared, session_id)
        return

    from core.goals_proactive_delivery import resolve_notify_channel, should_persist_admin_history

    notify_ch = resolve_notify_channel(prepared.payload)
    if not should_persist_admin_history(notify_ch, session_id):
        return
    user_label = (prepared.user_incoming or "").strip() or "[Revisión proactiva /crons]"
    user_sys = normalize_history_item({"role": "user", "content": user_label})
    assistant_sys = normalize_history_item({"role": "assistant", "content": reply_plain_for_storage})
    if not user_sys or not assistant_sys:
        return
    base_history = list(history_for_model or [])
    if not base_history:
        from core.chat_history import redis_load_chat_history

        try:
            base_history = await redis_load_chat_history(redis_client, tenant_id, session_id)
        except Exception:
            base_history = []
    saved_items = base_history + [user_sys, assistant_sys]
    await redis_save_chat_history(redis_client, tenant_id, session_id, saved_items)
    await upsert_conversation_meta(
        redis_client,
        tenant_id=tenant_id,
        session_id=session_id,
        actor=(username or "").strip() or "Sistema",
        effective_worker_id=effective_worker_id,
        worker_id=prepared.worker_id,
        user_message=user_label,
        assistant_message=reply_plain_for_storage,
        message_count=len(saved_items),
    )
    await _touch_loop_activity_if_configured(prepared, session_id)


async def _touch_loop_activity_if_configured(prepared: PreparedChatInvoke, session_id: str) -> None:
    """Ancla /loop --delta al último mensaje persistido."""
    vpath = (prepared.vault_db_path or "").strip()
    if not vpath or not session_id:
        return
    try:
        from duckclaw.commands.fast_replies import resolve_fly_command_text
        from duckclaw.commands.loop import is_loop_status_fly_text, touch_loop_last_activity

        fly_cmd = resolve_fly_command_text(
            user_incoming=prepared.user_incoming,
            message=prepared.message,
        )
        if is_loop_status_fly_text(
            prepared.user_incoming or "",
            prepared.message or "",
            fly_cmd,
        ):
            return
    except Exception:
        pass
    try:
        from duckclaw import DuckClaw
        from duckclaw.commands.loop import touch_loop_last_activity

        vdb = DuckClaw(vpath, read_only=False, engine="python")
        try:
            touch_loop_last_activity(
                vdb,
                session_id,
                tenant_id=(prepared.tenant_id or "default"),
            )
        finally:
            try:
                vdb.close()
            except Exception:
                pass
    except Exception:
        pass


async def upsert_conversation_meta(
    redis_client: Any,
    *,
    tenant_id: str,
    session_id: str,
    actor: str,
    effective_worker_id: str,
    worker_id: str,
    user_message: str,
    assistant_message: str,
    message_count: int,
) -> None:
    try:
        from core.admin_conversations import get_conversation_meta, upsert_conversation_meta as _upsert

        existing_conv = await get_conversation_meta(redis_client, tenant_id, session_id)
        conv_section = existing_conv.section if existing_conv else None
        await _upsert(
            redis_client,
            tenant_id=tenant_id,
            session_id=session_id,
            actor=actor,
            section=conv_section,
            last_worker_id=(effective_worker_id or worker_id or "").strip(),
            user_message=user_message,
            assistant_message=assistant_message,
            message_count=message_count,
        )
    except Exception:
        pass
