"""Dedicated thread pool for CPU/IO-heavy gateway work (never on the asyncio event loop)."""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Callable, TypeVar

_log = logging.getLogger(__name__)

T = TypeVar("T")

_executor: ThreadPoolExecutor | None = None


def _max_workers() -> int:
    raw = (os.environ.get("DUCKCLAW_GATEWAY_HEAVY_WORKERS") or "2").strip()
    try:
        return max(1, min(int(raw), 8))
    except ValueError:
        return 2


def heavy_work_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=_max_workers(),
            thread_name_prefix="duckclaw-gw-heavy",
        )
    return _executor


async def run_heavy_work(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Run blocking work off the event loop using the gateway heavy-work pool."""
    loop = asyncio.get_running_loop()
    bound = partial(func, *args, **kwargs)
    return await loop.run_in_executor(heavy_work_executor(), bound)


def schedule_heavy_work(coro_factory: Callable[[], Any]) -> asyncio.Task[Any]:
    """
    Fire-and-forget helper: ``coro_factory`` should return an awaitable, typically
    ``run_heavy_work(fn, ...)``.
    """

    async def _runner() -> Any:
        try:
            return await coro_factory()
        except Exception:
            _log.exception("scheduled heavy work failed")
            raise

    return asyncio.create_task(_runner(), name="gateway-heavy-work")
