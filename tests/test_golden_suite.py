"""Golden eval suite: checks, repeated runs, flaky classification and the regression gate."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from duckclaw.evals.golden_suite import check_case, load_cases, main, regressions, run_suite

FIX = Path(__file__).parent / "fixtures" / "evals" / "golden_example.yaml"
GOOD = {"reply": "I propose ACME at 10.", "tools": ["read_sql"]}


def test_checks_catch_each_kind_of_miss() -> None:
    case = {"must_not_call": ["place_order"], "must_call": ["read_sql"], "must_match": ["propos"], "must_not_match": ["sent"],
            "trajectory": {"start": ["read_sql"], "edges": {"read_sql": []}}}
    assert check_case(case, GOOD) == []
    bad = check_case(case, {"reply": "order sent", "tools": ["place_order"]})
    assert len(bad) >= 4 and any("forbidden tool place_order" in b for b in bad)


def test_regex_forbidden_tools_and_call_any() -> None:
    case = {"must_not_call_match": ["^(execute|place)_"], "must_call_any": ["read_sql", "get_quote"]}
    assert check_case(case, {"tools": ["get_quote", "propose_entry"]}) == []
    bad = check_case(case, {"tools": ["execute_new_thing", "web_search"]})
    assert any("matches /^(execute|place)_/" in b for b in bad) and any("called none of" in b for b in bad)
    assert check_case(case, {"tools": []}) == ["called none of ['read_sql', 'get_quote']"]


def test_runs_are_classified_always_pass_always_fail_or_flaky() -> None:
    cases = [{"id": "a", "must_match": ["ok"]}, {"id": "b", "must_match": ["ok"]}, {"id": "c", "must_match": ["ok"]}]
    calls = {"c": 0}

    def runner(case: dict) -> dict:
        if case["id"] == "c":
            calls["c"] += 1
            return {"reply": "ok" if calls["c"] % 2 else "nope"}
        return {"reply": "ok" if case["id"] == "a" else "nope"}

    r = run_suite(cases, runner, n=3)["cases"]
    assert (r["a"]["status"], r["b"]["status"], r["c"]["status"]) == ("always_pass", "always_fail", "flaky")
    assert r["c"]["passes"] == 2
    crashed = run_suite(cases, lambda c: 1 / 0, n=2)["cases"]["a"]
    assert crashed["status"] == "always_fail" and crashed["failures"][0].startswith("runner error")
    assert r["b"]["sample"] == {"tools": [], "reply": "nope", "spans": []} and "sample" not in r["a"]   # the last failed attempt, for the Evals tab


def test_regression_gate_only_trips_on_cases_that_always_passed() -> None:
    base = {"cases": {"x": {"status": "always_pass"}, "y": {"status": "flaky"}, "z": {"status": "always_pass"}}}
    now = {"cases": {"x": {"status": "flaky"}, "y": {"status": "always_fail"}}}
    assert regressions(base, now) == ["x", "z"]  # x got worse, z was dropped; y was never solid
    assert regressions(base, base) == []


def test_cli_end_to_end_with_the_example_goldens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = types.ModuleType("eval_runner_stub")
    mod.good = lambda case: {"reply": "I propose it. Returns allow 30 days.", "tools": ["read_sql"]}
    mod.bad = lambda case: {"reply": "Yes, you can. order sent", "tools": ["place_order"]}
    monkeypatch.setitem(sys.modules, "eval_runner_stub", mod)
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    assert len(load_cases(FIX)) == 2
    assert main([str(FIX), "--runner", "eval_runner_stub:good", "--out", str(first)]) == 0
    assert all(c["status"] == "always_pass" for c in json.loads(first.read_text())["cases"].values())
    assert main([str(FIX), "--runner", "eval_runner_stub:bad", "--out", str(second), "--baseline", str(first)]) == 1


def test_a_missing_span_is_not_a_skipped_action() -> None:
    case = {"id": "a", "must_call": ["read_sql"], "must_not_call": ["place_order"]}
    assert check_case(case, {"tools": []}) == ["did not call read_sql"]
    assert check_case(case, {"tools": [], "partial": True}) == []   # a delegate ran tools we cannot see
    assert check_case(case, {"tools": ["place_order"], "partial": True}) == ["called forbidden tool place_order"]   # what we do see still counts
    r = run_suite([case], lambda c: {"reply": "", "tools": ["place_order"], "partial": True, "spans": [{"name": "place_order", "input": '{"q": 1}', "output": "stub"}]}, n=1)["cases"]["a"]
    assert r["unverified"] and r["sample"]["spans"] == [{"name": "place_order", "input": '{"q": 1}', "output": "stub"}]


def test_requirements_are_loaded_and_carried_into_results(tmp_path: Path) -> None:
    from duckclaw.evals.golden_suite import load_requirements

    f = tmp_path / "g.yaml"
    f.write_text("""requirements:
  - {id: r1, text: t, question: q}
cases:
  - {id: a, requirement: r1, must_match: [ok]}
  - {id: b, must_match: [ok]}
""", encoding="utf-8")
    assert load_requirements(f) == [{"id": "r1", "text": "t", "question": "q"}] and load_requirements(FIX) == []
    r = run_suite(load_cases(f), lambda c: {"reply": "ok"}, n=1)["cases"]
    assert r["a"]["requirement"] == "r1" and "requirement" not in r["b"]


def test_claims_need_a_tool_and_variants_become_cases(tmp_path: Path) -> None:
    case = {"id": "a", "no_claim_without_tool": ["verificad"]}
    assert check_case(case, {"reply": "Todo verificado en DB", "tools": []}) == ["claims /verificad/ without any tool call"]
    assert check_case(case, {"reply": "Todo verificado en DB", "tools": ["read_sql"]}) == []
    assert check_case(case, {"reply": "No pude verificar", "tools": []}) == []
    f = tmp_path / "g.yaml"
    f.write_text("""cases:
  - {id: a, type: t, request: one, must_match: [ok], variants: [two, three]}
""", encoding="utf-8")
    got = load_cases(f)
    assert [(c["id"], c["request"]) for c in got] == [("a", "one"), ("a#v1", "two"), ("a#v2", "three")] and all(c["must_match"] == ["ok"] and "variants" not in c for c in got[1:])

