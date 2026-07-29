from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
from duckclaw.homeostasis.goals_alignment import (
    AlignmentReport,
    assess_goals_alignment,
    build_alignment_nudge_system_event,
    normalize_notify_channel,
    normalize_proactive_mode,
    pick_nudge_opener,
    refresh_goal_observations,
)
from duckclaw.graphs.on_the_fly_commands import (
    _extract_crons_delta_options,
    execute_goals,
    get_chat_state,
    set_chat_state,
    set_manager_goals,
)


def _make_db(path: Path) -> Any:
    from duckclaw import DuckClaw

    con = duckdb.connect(str(path))
    con.execute(
        """
        CREATE TABLE agent_config (
          key VARCHAR PRIMARY KEY,
          value TEXT,
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.close()
    return DuckClaw(str(path))


def test_normalize_notify_and_mode() -> None:
    assert normalize_notify_channel("admin") == "admin"
    assert normalize_notify_channel("BOTH") == "both"
    assert normalize_proactive_mode("always") == "always"
    assert normalize_proactive_mode("") == "on_misalignment"


def test_pick_nudge_opener_deterministic() -> None:
    a = pick_nudge_opener("chat-1", 1000.0)
    b = pick_nudge_opener("chat-1", 1000.0)
    c = pick_nudge_opener("chat-2", 1000.0)
    assert a == b
    assert a != c or len(a) > 0


def test_extract_crons_delta_options() -> None:
    parts, opts, err = _extract_crons_delta_options(
        ["--delta", "20min", "--notify", "admin", "--mode", "on_misalignment", "--jitter", "20%"]
    )
    assert err is None
    assert parts == ["20min"]
    assert opts["notify"] == "admin"
    assert opts["mode"] == "on_misalignment"


def test_build_alignment_nudge_system_event() -> None:
    report = AlignmentReport(
        aligned=False,
        misaligned_count=1,
        items=[],
        goals_count=1,
    )
    msg = build_alignment_nudge_system_event(report, chat_id="c1", epoch=1.0)
    assert msg.startswith("[SYSTEM_EVENT:")
    assert "Revisión de alineación con /goals" in msg


def test_assess_goals_alignment_anomaly(tmp_path: Path) -> None:
    db = _make_db(tmp_path / "a.duckdb")
    chat_id = "99"
    set_manager_goals(
        db,
        chat_id,
        [
            {
                "belief_key": "latency_ms",
                "target_value": 250.0,
                "threshold": 25.0,
                "observed_value": 400.0,
                "title": "Latency budget",
            }
        ],
    )
    set_chat_state(db, chat_id, "worker_id", "analytics-worker")
    report = assess_goals_alignment(db, chat_id, worker_id="analytics-worker")
    assert report.aligned is False
    assert report.misaligned_count >= 1


def test_refresh_goal_observations_preserves_persisted_observed_value(tmp_path: Path) -> None:
    db = _make_db(tmp_path / "b.duckdb")
    chat_id = "88"
    set_manager_goals(
        db,
        chat_id,
        [
            {
                "belief_key": "error_rate_pct",
                "target_value": 100.0,
                "threshold": 10.0,
                "observed_value": 250.5,
                "title": "Error rate",
            }
        ],
    )
    goals = refresh_goal_observations(db, chat_id, "analytics-worker")
    assert goals and float(goals[0].get("observed_value")) == 250.5


def test_assess_goals_alignment_percent_vs_absolute_mismatch_no_false_alarm(tmp_path: Path) -> None:
    """Without target_unit, large absolute observed vs percent target stays non-evaluable."""
    from duckclaw.homeostasis.goals_alignment import assess_goals_list_alignment

    db = _make_db(tmp_path / "mismatch.duckdb")
    chat_id = "unit-mismatch"
    goals = [
        {
            "belief_key": "metric_pct_limit",
            "target_value": 2.0,
            "threshold": 0.5,
            "observed_value": -3993.59,
            "title": "Metric within percent ceiling",
            "goal_kind": "monitor",
            "priority": 1,
        }
    ]
    report = assess_goals_list_alignment(db, chat_id, goals, worker_id="worker-a")
    assert report.aligned is True
    assert report.misaligned_count == 0
    assert report.items[0].scale_mismatch is True
    assert report.items[0].has_data is False


def test_execute_goals_delta_with_notify_and_mode(tmp_path: Path) -> None:
    db = _make_db(tmp_path / "c.duckdb")
    chat_id = "77"
    set_chat_state(db, chat_id, "worker_id", "analytics-worker")
    out = execute_goals(db, chat_id, "--delta 90s --notify admin --mode on_misalignment", tenant_id="T1")
    assert "Revisión proactiva" in out
    assert "admin" in out
    assert get_chat_state(db, chat_id, "goals_proactive_notify_channel") == "admin"
    meta = json.loads(get_chat_state(db, chat_id, "goals_delta_meta") or "{}")
    assert meta.get("mode") == "on_misalignment"
