"""Per-turn pack router (Jev): adds only packs above threshold, never blocks the turn on failure."""

import json

import pytest

from duckclaw.workers import tool_pack_router as r

RAW = {"router": {"kind": "jev", "threshold": 0.5, "packs": {"research": "buscar en internet", "mcp_google_gmail": "leer correos", "mcp_gone": "x"}}}


@pytest.fixture(autouse=True)
def _clear_cache():
    r._ask.cache_clear()


def _stub(monkeypatch, answers=None, ok=True, calls=None):
    def fake(state, questions_json, model="", timeout=60, **_):
        if calls is not None:
            calls.append(sorted(json.loads(questions_json)))
        if not ok:
            return json.dumps({"ok": False, "error": "http_500"})
        return json.dumps({"ok": True, "answers": {k: {"type": "noul", "noul": v} for k, v in (answers or {}).items()}})

    monkeypatch.setattr("duckclaw.forge.skills.jev_decide_bridge.jev_decide_impl", fake)


def test_activates_only_packs_above_threshold_and_known(monkeypatch):
    calls = []
    _stub(monkeypatch, {"research": 0.9, "mcp_google_gmail": 0.2}, calls=calls)
    got = r.route_packs(RAW, "noticias de Ormuz", {"research", "mcp_google_gmail"})
    assert got == {"research"}
    assert calls == [["mcp_google_gmail", "research"]]  # mcp_gone is not available: not asked


def test_one_call_per_turn(monkeypatch):
    calls = []
    _stub(monkeypatch, {"research": 0.9}, calls=calls)
    for _ in range(4):  # the agent node re-filters tools every LLM round
        r.route_packs(RAW, "noticias", {"research"})
    assert len(calls) == 1


def test_failure_or_no_router_adds_nothing(monkeypatch):
    _stub(monkeypatch, ok=False)
    assert r.route_packs(RAW, "noticias", {"research"}) == frozenset()
    assert r.route_packs({}, "noticias", {"research"}) == frozenset()
    assert r.route_packs({"router": {"kind": "other", "packs": {"a": "b"}}}, "x", {"a"}) == frozenset()
