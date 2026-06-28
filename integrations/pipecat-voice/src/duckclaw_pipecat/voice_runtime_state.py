"""Mutable per-call runtime (app_state from RTVI client messages)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VoiceRuntimeState:
    """Session-scoped mutable state alongside frozen VoiceSessionContext."""

    app_state: dict[str, Any] = field(default_factory=dict)

    def merge_app_state(self, payload: dict[str, Any]) -> None:
        if not payload:
            return
        self.app_state.update(payload)
