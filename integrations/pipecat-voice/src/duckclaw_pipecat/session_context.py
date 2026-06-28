"""Per-call WebRTC session identity (worker, tenant, chat_id)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceSessionContext:
    session_id: str
    worker_id: str
    tenant_id: str
    chat_id: str
    actor_email: str

    @classmethod
    def create(
        cls,
        *,
        default_worker: str = "default",
        default_tenant: str = "default",
        worker_id: str | None = None,
        tenant_id: str | None = None,
        session_id: str | None = None,
        actor_email: str | None = None,
    ) -> VoiceSessionContext:
        sid = (session_id or "").strip() or f"voice-{uuid.uuid4()}"
        wid = (worker_id or default_worker or "default").strip() or "default"
        tid = (tenant_id or default_tenant or "default").strip() or "default"
        actor = (actor_email or "voice-pipecat").strip() or "voice-pipecat"
        return cls(session_id=sid, worker_id=wid, tenant_id=tid, chat_id=sid, actor_email=actor)
