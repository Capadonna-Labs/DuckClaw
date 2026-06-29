"""Emit progress phrase while graph HTTP invoke is in-flight."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from duckclaw_pipecat.graph_bridge import GraphBridgeOutcome


async def invoke_graph_with_progress(
    invoke_coro: Callable[[], Awaitable[GraphBridgeOutcome]],
    *,
    progress_phrase: str,
    delay_sec: float,
    on_progress: Callable[[str], Awaitable[None]] | None = None,
) -> GraphBridgeOutcome:
    """
    Run gateway invoke; after delay_sec emit progress_phrase once if still waiting.
    Cancels progress timer when invoke completes (success or classified error).
    """
    invoke_task = asyncio.create_task(invoke_coro())
    progress_emitted = False

    async def _maybe_progress() -> None:
        nonlocal progress_emitted
        try:
            await asyncio.sleep(max(0.1, delay_sec))
            if not invoke_task.done() and on_progress is not None and not progress_emitted:
                progress_emitted = True
                result = on_progress(progress_phrase)
                if asyncio.iscoroutine(result):
                    await result
        except asyncio.CancelledError:
            return

    progress_task = asyncio.create_task(_maybe_progress())
    try:
        return await invoke_task
    finally:
        progress_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await progress_task
