"""Reintento en grafo para Regla de Evidencia Única (set_reply → agent)."""

from __future__ import annotations

import pytest

from duckclaw.egress.evidence_validator import (
    VISUAL_EVIDENCE_RETRY_REASON,
    enforce_visual_evidence_rule,
    visual_evidence_retry_system_message,
)
from duckclaw.workers.factory import _visual_evidence_max_retries


def _route_after_set_reply(state: dict) -> str:
    """Misma lógica que WorkerFactory.route_after_set_reply."""
    return "agent" if state.get("visual_evidence_graph_retry") else "end"


def test_visual_evidence_retry_reason_constant() -> None:
    _, reason = enforce_visual_evidence_rule(
        incoming="x\n[VLM_CONTEXT h=1]",
        messages=[],
        reply="SPY cotiza 450.25",
    )
    assert reason == VISUAL_EVIDENCE_RETRY_REASON


def test_gateway_vlm_block_skips_visual_evidence_audit() -> None:
    reply, reason = enforce_visual_evidence_rule(
        incoming=(
            "Analiza\nContexto visual adjunto: Nikkei 225 2.73% ▼\n"
            "[VLM_CONTEXT image_hash=abc confidence=0.85]"
        ),
        messages=[],
        reply="El Nikkei 225 cerró con -2.73% hoy.",
    )
    assert reason is None
    assert "2.73" in reply


def test_route_after_set_reply_when_retry_flag() -> None:
    assert _route_after_set_reply({"visual_evidence_graph_retry": True}) == "agent"
    assert _route_after_set_reply({"visual_evidence_graph_retry": False}) == "end"
    assert _route_after_set_reply({}) == "end"


def test_visual_evidence_max_retries_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_VISUAL_EVIDENCE_MAX_RETRIES", raising=False)
    assert _visual_evidence_max_retries() == 1


def test_visual_evidence_max_retries_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_VISUAL_EVIDENCE_MAX_RETRIES", "2")
    assert _visual_evidence_max_retries() == 2


def test_retry_scheduling_decision_under_max() -> None:
    """Simula set_reply: count < max → debe programar reintento."""
    max_r = 1
    count = 0
    _, reason = enforce_visual_evidence_rule(
        incoming="x\n[VLM_CONTEXT h=1]",
        messages=[],
        reply="VIX 24.55",
    )
    assert reason == VISUAL_EVIDENCE_RETRY_REASON
    assert count < max_r
    next_state = {
        "visual_evidence_retry_count": count + 1,
        "visual_evidence_graph_retry": True,
        "reply": "",
    }
    assert _route_after_set_reply(next_state) == "agent"


def test_retry_scheduling_decision_when_exhausted() -> None:
    max_r = _visual_evidence_max_retries()
    count = max_r
    assert not (count < max_r)
    assert _route_after_set_reply({"visual_evidence_graph_retry": False}) == "end"


def test_visual_evidence_retry_system_message_is_system_role() -> None:
    from langchain_core.messages import SystemMessage

    msg = visual_evidence_retry_system_message()
    assert isinstance(msg, SystemMessage)
