"""Tests for record_operational_lesson forge skill."""

from __future__ import annotations

import json

from duckclaw.forge.skills.record_operational_lesson_bridge import (
    _record_operational_lesson_impl,
    register_record_operational_lesson_skill,
)


def test_register_record_operational_lesson_skill_adds_tool() -> None:
    tools: list = []
    register_record_operational_lesson_skill(tools, {})
    names = {getattr(t, "name", "") for t in tools}
    assert "record_operational_lesson" in names


def test_record_operational_lesson_persists_with_lesson_type(monkeypatch) -> None:
    calls: list[tuple] = []

    class _Db:
        schema = "finance_worker"

    def _fake_persist(db, schema, key, trigger, lesson, conf):
        calls.append((schema, key, trigger, lesson, conf))

    monkeypatch.setattr(
        "duckclaw.forge.skills.record_operational_lesson_bridge.persist_field_lesson",
        _fake_persist,
    )
    out = json.loads(
        _record_operational_lesson_impl(
            "Nunca citar qty sin snapshot IBKR",
            context_trigger="audit mismatch AAPL",
            lesson_type="broker_position_hallucination",
            confidence_score=0.95,
            db=_Db(),
        )
    )
    assert out["ok"] is True
    assert out["context_trigger"] == "broker_position_hallucination:audit mismatch AAPL"
    assert out["belief_key"].startswith("lesson_")
    assert calls and calls[0][0] == "finance_worker"
    assert calls[0][2] == "broker_position_hallucination:audit mismatch AAPL"


def test_register_skips_when_tool_already_present() -> None:
    class _Existing:
        name = "record_operational_lesson"

    tools: list = [_Existing()]
    register_record_operational_lesson_skill(tools, {})
    assert len(tools) == 1
