"""Background consumer for ``duckclaw:telegram_inbound_updates`` (Gateway only)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from duckclaw.telegram_inbound_queue import dequeue_telegram_update, telegram_inbound_queue_enabled

_log = logging.getLogger("duckclaw.gateway.telegram_inbound_consumer")


async def run_telegram_inbound_consumer_cycle(
    *,
    app: Any,
    invoke_agent_chat: Callable[..., Awaitable[Any]],
    resolve_effective_telegram_bot_token: Callable[[], str],
    block_timeout_sec: float = 2.0,
) -> bool:
    """Pop one queued job (sync Redis in thread) and invoke chat. Returns True if a job ran."""
    if not telegram_inbound_queue_enabled():
        return False
    job = await asyncio.to_thread(dequeue_telegram_update, block_timeout_sec=block_timeout_sec)
    if not job:
        return False
    from routers.telegram_inbound_webhook import telegram_invoke_agent_chat_and_reply

    redis_client = getattr(app.state, "redis", None)
    telegram_mcp = getattr(app.state, "telegram_mcp", None)
    try:
        await telegram_invoke_agent_chat_and_reply(
            message=str(job.get("message") or ""),
            chat_id=job.get("chat_id"),
            user_id=str(job.get("user_id") or ""),
            username=str(job.get("username") or "Usuario"),
            chat_type=str(job.get("chat_type") or "private"),
            tenant_id=str(job.get("tenant_id") or ""),
            worker_id=str(job.get("worker_id") or ""),
            session_id=str(job.get("session_id") or job.get("chat_id") or ""),
            reply_token=str(job.get("reply_token") or "").strip() or None,
            telegram_forced_vault_db_path=job.get("telegram_forced_vault_db_path"),
            invoke_agent_chat=invoke_agent_chat,
            resolve_effective_telegram_bot_token=resolve_effective_telegram_bot_token,
            redis_client=redis_client,
            telegram_mcp=telegram_mcp,
        )
    except Exception as exc:  # noqa: BLE001
        _log.exception(
            "telegram inbound consumer failed job_id=%s chat_id=%s: %s",
            job.get("job_id"),
            job.get("chat_id"),
            exc,
        )
    return True


async def telegram_inbound_consumer_loop(
    *,
    app: Any,
    invoke_agent_chat: Callable[..., Awaitable[Any]],
    resolve_effective_telegram_bot_token: Callable[[], str],
) -> None:
    """Long-running loop; cancel via task shutdown in lifespan."""
    _log.info("telegram inbound Redis consumer started (queue=%s)", "duckclaw:telegram_inbound_updates")
    while True:
        try:
            processed = await run_telegram_inbound_consumer_cycle(
                app=app,
                invoke_agent_chat=invoke_agent_chat,
                resolve_effective_telegram_bot_token=resolve_effective_telegram_bot_token,
                block_timeout_sec=2.0,
            )
            if not processed:
                await asyncio.sleep(0.25)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            _log.warning("telegram inbound consumer loop error: %s", exc)
            await asyncio.sleep(1.0)
