"""Smoke / manual checklist for DuckClaw-Voice (Pipecat)."""

from __future__ import annotations

import pytest

pytest.importorskip("pipecat", reason="realtime extra required")


def test_duckclaw_graph_llm_builds_processor() -> None:
    from duckclaw_pipecat.config import VoiceSettings
    from duckclaw_pipecat.processors.duckclaw_graph_llm import DuckClawGraphLLM
    from duckclaw_pipecat.session_context import VoiceSessionContext

    settings = VoiceSettings(
        duckclaw_voice_gateway_url="http://127.0.0.1:8000",
        duckclaw_voice_gateway_admin_key="test",
    )
    session = VoiceSessionContext.create(default_worker="default", default_tenant="default")
    processor = DuckClawGraphLLM.build(session=session, settings=settings)
    assert processor is not None
