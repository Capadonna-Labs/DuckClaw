"""Pub/sub de actualización de custom reports → SSE admin."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

_log = logging.getLogger(__name__)

REPORT_UPDATE_CHANNEL_PREFIX = "duckclaw:report-update:"


def report_update_channel(report_id: str) -> str:
    rid = str(report_id or "").strip() or "unknown"
    return f"{REPORT_UPDATE_CHANNEL_PREFIX}{rid}"


async def iter_report_reload_events(
    redis_client: Any,
    report_id: str,
    *,
    stop: asyncio.Event | None = None,
) -> AsyncIterator[str]:
    """Escucha ``reload`` en Redis hasta cancelación."""
    if redis_client is None:
        return
    channel = report_update_channel(report_id)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    try:
        while stop is None or not stop.is_set():
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.25)
            if not msg:
                await asyncio.sleep(0.05)
                continue
            if msg.get("type") != "message":
                continue
            data = msg.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")
            if str(data or "").strip() == "reload":
                yield "reload"
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        _log.debug("report reload listener stopped report_id=%r: %s", report_id, exc)
    finally:
        try:
            await pubsub.unsubscribe(channel)
        except Exception:
            pass
        try:
            await pubsub.aclose()
        except Exception:
            pass
