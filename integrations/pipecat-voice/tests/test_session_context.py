"""Tests for VoiceSessionContext."""

from __future__ import annotations

from duckclaw_pipecat.session_context import VoiceSessionContext


def test_create_uses_defaults() -> None:
    ctx = VoiceSessionContext.create(default_worker="default", default_tenant="default")
    assert ctx.worker_id == "default"
    assert ctx.tenant_id == "default"
    assert ctx.chat_id == ctx.session_id
    assert ctx.session_id.startswith("voice-")


def test_create_respects_overrides() -> None:
    ctx = VoiceSessionContext.create(
        default_worker="default",
        default_tenant="default",
        worker_id="custom",
        tenant_id="t1",
        session_id="voice-fixed",
    )
    assert ctx.worker_id == "custom"
    assert ctx.tenant_id == "t1"
    assert ctx.session_id == "voice-fixed"
    assert ctx.chat_id == "voice-fixed"
