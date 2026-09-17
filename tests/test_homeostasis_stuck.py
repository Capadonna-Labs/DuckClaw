"""Tests for evaluate_homeostasis stuck fingerprint / escalate."""

from __future__ import annotations

from pathlib import Path

from duckclaw.workers.homeostasis_stuck import (
    build_stuck_nudge_message,
    fingerprint_homeostasis_payload,
    is_misaligned_without_hitl,
    record_homeostasis_observation,
)
from duckclaw.workers.tool_invocation_policy import decide_loop_homeostasis_tool_invocation


def _payload(**overrides):
    base = {
        "metrics_aligned": False,
        "homeostasis_achieved": False,
        "hitl_required": False,
        "deviations": {"exposure": {"delta": 1.2}},
    }
    base.update(overrides)
    return base


def test_is_misaligned_without_hitl() -> None:
    assert is_misaligned_without_hitl(_payload())
    assert not is_misaligned_without_hitl(_payload(metrics_aligned=True, homeostasis_achieved=True))
    assert not is_misaligned_without_hitl(_payload(hitl_required=True))


def test_fingerprint_stable_for_same_slice() -> None:
    a = fingerprint_homeostasis_payload(_payload())
    b = fingerprint_homeostasis_payload(_payload())
    assert a == b
    c = fingerprint_homeostasis_payload(_payload(deviations={"other": 1}))
    assert a != c


def test_record_homeostasis_observation_escalates_after_streak(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_HOMEOSTASIS_STUCK_STREAK", "3")
    from duckclaw import DuckClaw

    db_path = tmp_path / "h.duckdb"
    db = DuckClaw(str(db_path), read_only=False)
    chat_id = "admin-conv-test"
    data = _payload()
    r1 = record_homeostasis_observation(db, chat_id, data, tenant_id="default")
    assert r1["action"] == "nudge"
    assert r1["streak"] == 1
    r2 = record_homeostasis_observation(db, chat_id, data, tenant_id="default")
    assert r2["action"] == "nudge"
    assert r2["streak"] == 2
    r3 = record_homeostasis_observation(db, chat_id, data, tenant_id="default")
    assert r3["action"] == "escalate"
    assert r3["streak"] == 3
    cleared = record_homeostasis_observation(
        db, chat_id, _payload(metrics_aligned=True, homeostasis_achieved=True), tenant_id="default"
    )
    assert cleared["action"] == "clear"
    db.close()


def test_decide_loop_skips_force_when_streak_at_limit(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_HOMEOSTASIS_STUCK_STREAK", "3")
    incoming = "[SYSTEM_EVENT: Ciclo de auto-mejora /loop — revisa homeostasis]"
    d = decide_loop_homeostasis_tool_invocation(
        incoming=incoming,
        available_tools=["evaluate_homeostasis", "read_sql"],
        homeostasis_streak=3,
    )
    assert not d.should_force
    d2 = decide_loop_homeostasis_tool_invocation(
        incoming=incoming,
        available_tools=["evaluate_homeostasis", "read_sql"],
        homeostasis_streak=0,
    )
    assert d2.should_force
    assert d2.tool_name == "evaluate_homeostasis"


def test_build_stuck_nudge_message_mentions_escalate() -> None:
    msg = build_stuck_nudge_message(streak=3, corrective_tools=["calculate_tp_sl_distance"], escalate=True)
    assert "LOOP_HOMEOSTASIS_STUCK" in msg
    assert "escalate_stuck=true" in msg
