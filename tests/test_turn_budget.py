"""Per-turn LLM spend cap: charged by the OpenRouter client, enforced before the next call."""

from __future__ import annotations

import pytest

from duckclaw.integrations.llm_providers import build_openrouter_llm
from duckclaw.turn_budget import TurnBudgetExceeded, charge_turn_spend, check_turn_budget, track_turn_spend


def _response(usage: dict) -> dict:
    return {"id": "gen-1", "model": "m", "provider": "p", "usage": usage,
            "choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}]}


def test_budget_trips_at_cap_and_is_off_outside_a_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_TURN_BUDGET_USD", "0.50")
    charge_turn_spend(99)  # no open turn: ignored
    check_turn_budget()
    with track_turn_spend() as box:
        charge_turn_spend(0.49)
        check_turn_budget()
        charge_turn_spend(0.01)
        with pytest.raises(TurnBudgetExceeded):
            check_turn_budget()
        assert box[0] == pytest.approx(0.50)
    check_turn_budget()


def test_cap_zero_disables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_TURN_BUDGET_USD", "0")
    with track_turn_spend():
        charge_turn_spend(100)
        check_turn_budget()


def test_openrouter_client_charges_and_halts_the_next_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test_dummy")
    monkeypatch.setenv("DUCKCLAW_TURN_BUDGET_USD", "0.50")
    llm = build_openrouter_llm()
    with track_turn_spend() as box:
        llm._create_chat_result(_response({"prompt_tokens": 1_000_000, "completion_tokens": 0, "cost": 0.30}))
        assert box[0] == pytest.approx(0.30)  # OpenRouter's own cost wins over the flat estimate
        llm._create_chat_result(_response({"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}))
        assert box[0] == pytest.approx(0.30 + 0.15 + 0.60)  # no cost field: flat per-million estimate
        with pytest.raises(TurnBudgetExceeded):
            llm.invoke("hello")  # raises before any network call
