"""Inference concurrency control for unified Apple Silicon memory."""

from __future__ import annotations

import asyncio
import os

_MAX = int((os.environ.get("DUCKCLAW_SENSORY_MAX_CONCURRENT") or "2").strip() or "2")
INFERENCE_SEM = asyncio.Semaphore(max(1, _MAX))


async def acquire_inference_slot() -> None:
    await INFERENCE_SEM.acquire()


def release_inference_slot() -> None:
    INFERENCE_SEM.release()


def semaphore_available() -> int:
    """Approximate free slots (internal _value)."""
    return getattr(INFERENCE_SEM, "_value", 0)
