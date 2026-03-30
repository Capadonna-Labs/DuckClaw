"""Pacing y backoff ante HTTP 429 (Bot API)."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

# Telegram: ~30 mensajes/s por bot en un mismo chat (conservador global).
_MIN_INTERVAL_SEC = 1.0 / 30.0
_lock = threading.Lock()
_next_ok = 0.0


def pace_before_request() -> None:
    global _next_ok
    with _lock:
        now = time.monotonic()
        if now < _next_ok:
            time.sleep(max(0.0, _next_ok - now))
        _next_ok = time.monotonic() + _MIN_INTERVAL_SEC


def retry_after_sec_from_telegram_body(raw: str) -> float | None:
    """Extrae retry_after del JSON de error de Telegram si existe."""
    s = (raw or "").strip()
    if "{" not in s:
        return None
    start = s.find("{")
    try:
        data: Any = json.loads(s[start:])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    params = data.get("parameters")
    if isinstance(params, dict) and params.get("retry_after") is not None:
        try:
            return float(params["retry_after"])
        except (TypeError, ValueError):
            pass
    return None
