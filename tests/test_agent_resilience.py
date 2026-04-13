"""Tests para replan del Manager y utilidades en agent_resilience."""

from __future__ import annotations

import pytest

from duckclaw.graphs import agent_resilience as ar


def test_plan_max_attempts_from_env_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_AGENT_MAX_PLAN_ATTEMPTS", raising=False)
    assert ar.plan_max_attempts_from_env() == 3


def test_plan_max_attempts_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_AGENT_MAX_PLAN_ATTEMPTS", "99")
    assert ar.plan_max_attempts_from_env() == 10
    monkeypatch.setenv("DUCKCLAW_AGENT_MAX_PLAN_ATTEMPTS", "0")
    assert ar.plan_max_attempts_from_env() == 1


def test_replan_enabled_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_AGENT_REPLAN_STRATEGY", "off")
    assert ar.replan_enabled() is False


def test_replan_enabled_on_like_hybrid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_AGENT_REPLAN_STRATEGY", "on")
    assert ar.replan_enabled() is True


def test_format_exhausted_dedupes_reasons() -> None:
    text = ar.format_exhausted_plan_failure(["a", "a", "b"])
    assert "a" in text and "b" in text


def test_classify_exception_duckdb_clash_not_replan() -> None:
    exc = RuntimeError("same database file opened with different configuration")
    ok, reason = ar.classify_exception_for_replan(exc, duckdb_config_clash=True)
    assert ok is False
    assert "duckdb" in reason.lower()


def test_worker_reply_suggests_replan() -> None:
    assert ar.worker_reply_suggests_replan_without_tools("No pude completar la inferencia (MLX).") is True
    assert ar.worker_reply_suggests_replan_without_tools("Aquí tienes el saldo en pesos.") is False


def test_resilience_escalation_wants_read_sql() -> None:
    assert ar.resilience_escalation_wants_read_sql("¿Cuánto tengo en la cuenta corriente?", 1) is True
    assert ar.resilience_escalation_wants_read_sql("hola", 1) is False
    assert ar.resilience_escalation_wants_read_sql("datos duckdb tablas", 2) is True


def test_merge_failure_reasons() -> None:
    assert ar.merge_failure_reasons(["x"], "y") == ["x", "y"]
    assert ar.merge_failure_reasons(None, "z") == ["z"]


def test_format_replan_task_suffix_contains_attempt() -> None:
    s = ar.format_replan_task_suffix(1, 3)
    assert "2/3" in s or "intento 2" in s.lower()


@pytest.mark.parametrize(
    "strategy, expected",
    [
        ("hybrid", True),
        ("off", False),
    ],
)
def test_replan_strategy(monkeypatch: pytest.MonkeyPatch, strategy: str, expected: bool) -> None:
    monkeypatch.setenv("DUCKCLAW_AGENT_REPLAN_STRATEGY", strategy)
    assert ar.replan_enabled() is expected
    monkeypatch.delenv("DUCKCLAW_AGENT_REPLAN_STRATEGY", raising=False)


def test_plan_max_attempts_invalid_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_AGENT_MAX_PLAN_ATTEMPTS", "not-a-number")
    assert ar.plan_max_attempts_from_env() == 3
