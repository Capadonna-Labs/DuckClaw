"""Health metrics for sensory_node."""

from __future__ import annotations

import sys
import time
from typing import Any

from duckclaw_sensory_node.concurrency import semaphore_available

_START_TIME = time.monotonic()


def vram_peak_gb() -> float | None:
    if sys.platform != "darwin":
        return None
    try:
        import mlx.core as mx

        peak = mx.get_peak_memory()
        return round(float(peak) / 1e9, 3)
    except Exception:
        return None


def build_health_payload(*, stt_loaded: bool, tts_loaded: bool) -> dict[str, Any]:
    return {
        "stt_loaded": stt_loaded,
        "tts_loaded": tts_loaded,
        "vram_peak_gb": vram_peak_gb(),
        "semaphore_available": semaphore_available(),
        "uptime_s": round(time.monotonic() - _START_TIME, 1),
        "platform": sys.platform,
    }
