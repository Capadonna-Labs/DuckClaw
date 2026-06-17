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
    if redis_client is None or not gateway_chat_history_enabled() or not (reply_plain_for_storage or "").strip():
        return
    tenant_id = prepared.tenant_id
    session_id = prepared.session_id
    if not prepared.is_system_prompt:
        user_item = normalize_history_item({"role": "user", "content": message})
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
            user_message=message,
            assistant_message=reply_plain_for_storage,
            message_count=len(saved_items),
        )
        return

    from core.goals_proactive_delivery import resolve_notify_channel, should_persist_admin_history

    notify_ch = resolve_notify_channel(prepared.payload)
    if not should_persist_admin_history(notify_ch, session_id):
        return
    user_sys = normalize_history_item({"role": "user", "content": "[Revisión proactiva /crons]"})
    assistant_sys = normalize_history_item({"role": "assistant", "content": reply_plain_for_storage})
    if not user_sys or not assistant_sys:
        return
    saved_items = history_for_model + [user_sys, assistant_sys]
    await redis_save_chat_history(redis_client, tenant_id, session_id, saved_items)
    await upsert_conversation_meta(
        redis_client,
        tenant_id=tenant_id,
        session_id=session_id,
        actor=(username or "").strip() or "Sistema",
        effective_worker_id=effective_worker_id,
        worker_id=prepared.worker_id,
        user_message="[Revisión proactiva /crons]",
        assistant_message=reply_plain_for_storage,
        message_count=len(saved_items),
    )


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
