"""Fire-and-forget background tasks for request handlers, GC-safe.

``asyncio.create_task()`` only holds a weak reference to the task; with
nothing else referencing it, the event loop is free to garbage-collect it
before it ever runs — especially when the enclosing request handler returns
right after creating it. Keep a strong reference until each task finishes.
See: https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
"""

from __future__ import annotations

import asyncio
from typing import Any

_background_tasks: set[asyncio.Task[Any]] = set()


def spawn_background(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
