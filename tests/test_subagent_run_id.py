"""Secuencia incremental de subagentes (manager → worker)."""

import pytest

from duckclaw.graphs import subagent_run_id as m


def test_next_subagent_run_number_fallback_increments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("DUCKCLAW_REDIS_URL", raising=False)
    tid = f"tenant-{id(monkeypatch)}"
    assert m.next_subagent_run_number(tid, "SIATA-Analyst") == 1
    assert m.next_subagent_run_number(tid, "SIATA-Analyst") == 2
    assert m.next_subagent_run_number(tid, "BI-Analyst") == 1
    assert m.next_subagent_run_number(f"{tid}-b", "SIATA-Analyst") == 1
