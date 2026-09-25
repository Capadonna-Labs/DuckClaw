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


def test_fingerprint_tolerates_numeric_jitter() -> None:
    a = fingerprint_homeostasis_payload(_payload(deviations={"exposure": {"delta": 1.201}}))
    b = fingerprint_homeostasis_payload(_payload(deviations={"exposure": {"delta": 1.209}}))
    # Nested dicts fingerprint on skill/status/breached — not raw delta floats.
    assert a == b
    d1 = fingerprint_homeostasis_payload(_payload(deviations={"exposure": 1.201}))
    d2 = fingerprint_homeostasis_payload(_payload(deviations={"exposure": 1.204}))
    assert d1 == d2  # round(..., 2)
    d3 = fingerprint_homeostasis_payload(_payload(deviations={"exposure": 1.30}))
    assert d1 != d3


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


def test_build_loop_homeostasis_detente_misaligned() -> None:
    from duckclaw.workers.homeostasis_stuck import build_loop_homeostasis_detente_message

    msg = build_loop_homeostasis_detente_message(_payload())
    assert "LOOP_HOMEOSTASIS_DETENTE" in msg
    assert "DETENTE" in msg
    assert "read_sql" in msg
    assert "timestamp" in msg
    assert "run_sandbox" in msg or "sandbox" in msg
    assert "trading" in msg


def test_build_loop_homeostasis_detente_aligned() -> None:
    from duckclaw.workers.homeostasis_stuck import build_loop_homeostasis_detente_message

    msg = build_loop_homeostasis_detente_message(
        _payload(metrics_aligned=True, homeostasis_achieved=True)
    )
    assert "request_homeostasis_validation" in msg


def test_maybe_append_uses_system_message_not_human(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_HOMEOSTASIS_STUCK_STREAK", "3")
    from duckclaw import DuckClaw
    from duckclaw.workers.homeostasis_stuck import maybe_append_homeostasis_stuck_nudge
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

    db_path = tmp_path / "h2.duckdb"
    db = DuckClaw(str(db_path), read_only=False)
    import json

    tool = ToolMessage(
        content=json.dumps(_payload()),
        tool_call_id="t1",
        name="evaluate_homeostasis",
    )
    out = maybe_append_homeostasis_stuck_nudge(
        [HumanMessage(content="[SYSTEM_EVENT: Ciclo /loop]"), tool],
        db=db,
        state={"chat_id": "admin-conv-x", "tenant_id": "default"},
    )
    assert len(out) >= 3
    assert isinstance(out[-1], SystemMessage) or isinstance(out[-2], SystemMessage)
    assert not any(isinstance(m, HumanMessage) and "LOOP_HOMEOSTASIS" in str(m.content) for m in out)
    assert any("LOOP_HOMEOSTASIS_DETENTE" in str(getattr(m, "content", "")) for m in out)
    db.close()


def test_apply_terminal_clears_read_sql_after_evaluate_on_loop() -> None:
    from duckclaw.workers.factory_graph_nodes_agent_policy_early_context import (
        apply_terminal_force_tool_overrides,
    )

    incoming = "[SYSTEM_EVENT: Ciclo de auto-mejora programado /loop. Metas (/goals): SL.]"
    (
        orch,
        force_schema,
        force_admin,
        force_read,
        force_tavily,
        force_reddit,
        force_visual,
    ) = apply_terminal_force_tool_overrides(
        incoming=incoming,
        orch_incoming=incoming,
        intent_incoming=incoming,
        tools_by_name={"evaluate_homeostasis": object(), "read_sql": object()},
        called_tools_since_last_human={"evaluate_homeostasis"},
        already_has_tool_result=False,
        telegram_context_summarize_directive=False,
        summarize_stored_directive=False,
        use_heuristic_first_tool=True,
        force_orch_tool="read_sql",
        force_schema=False,
        force_admin_sql=False,
        force_read_sql=True,
        force_tavily=False,
        force_reddit=False,
        force_visual=False,
        homeostasis_streak=1,
    )
    assert force_read is False
    assert force_admin is False
    assert orch is None
    assert force_schema is False
    assert force_tavily is False
    assert force_reddit is False
    assert force_visual is False
