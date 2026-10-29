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
