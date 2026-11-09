"""Spots an agent repeating itself: the same signature N times in a row for one key."""

from __future__ import annotations

import threading
from collections import deque


class StallDetector:
    # ponytail: in-memory and per process; persist the history if a stall must survive a restart.
    def __init__(self, repeats: int = 3, max_keys: int = 256) -> None:
        self._repeats = max(2, int(repeats))
        self._max_keys = max(1, int(max_keys))
        self._lock = threading.Lock()
        self._seen: dict[str, deque[str]] = {}

    def observe(self, key: str, signature: str) -> bool:
        """True when the last ``repeats`` signatures for ``key`` are identical; the history then restarts, so a stall that goes on alerts again only after another ``repeats`` rounds."""
        with self._lock:
            hist = self._seen.setdefault(key, deque(maxlen=self._repeats))
            hist.append(signature)
            while len(self._seen) > self._max_keys:
                self._seen.pop(next(iter(self._seen)))
            stalled = len(hist) == self._repeats and len(set(hist)) == 1
            if stalled:
                hist.clear()
            return stalled


__all__ = ["StallDetector"]
