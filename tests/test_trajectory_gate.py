"""Trajectory gate: the golden corpus passes, and every kind of deviation is caught."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw.traces.trajectory_gate import check_corpus, check_trajectory, load_golden, main, read_records

FIX = Path(__file__).parent / "fixtures" / "trajectories"


@pytest.fixture(scope="module")
def golden() -> dict:
    return load_golden(FIX / "golden.yaml")


def test_recorded_corpus_follows_the_golden_dag(golden: dict) -> None:
    assert check_corpus(read_records(FIX), golden) == []


@pytest.mark.parametrize("tools, needle", [
    (["read_sql", "drop_table"], "forbidden"),
    (["read_sql", "send_email"], "not in the golden DAG"),
    (["request_approval"], "may not open a turn"),
    (["read_sql", "write_record"], "not an edge"),
    (["write_record"], "may not open a turn"),
    (["invoke_worker", "run_sandbox"], "not an edge"),
])
def test_deviations_are_caught(golden: dict, tools: list[str], needle: str) -> None:
    assert any(needle in v for v in check_trajectory(tools, golden)), check_trajectory(tools, golden)


def test_skipped_safety_step_is_caught_even_when_the_edge_exists(golden: dict) -> None:
    golden = {**golden, "edges": {**golden["edges"], "read_sql": ["write_record"]}}
    assert any("without request_approval" in v for v in check_trajectory(["read_sql", "write_record"], golden))


def test_cli_exit_code_blocks_a_bad_corpus(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"session_id":"x","context":{"request":"r"},"action":{"tool":"drop_table"}}\n', encoding="utf-8")
    assert main([str(FIX / "golden.yaml"), str(FIX)]) == 0
    assert main([str(FIX / "golden.yaml"), str(bad)]) == 1
