"""Tests for /goals homeostasis manifest CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import duckdb
import pytest

from duckclaw.graphs.on_the_fly_commands import execute_homeostasis_goals, set_manager_goals
from harness_core.states.meditate_state import DomainGoal, HomeostasisManifest


def _make_db(path: Path) -> Any:
    from duckclaw import DuckClaw

    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA IF NOT EXISTS harness_core")
    con.execute(
        """
        CREATE TABLE harness_core.homeostasis_targets (
            tenant_id VARCHAR PRIMARY KEY,
            targets_json JSON,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
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


def test_execute_homeostasis_goals_list_empty(tmp_path: Path) -> None:
    db = _make_db(tmp_path / "list.duckdb")
    out = execute_homeostasis_goals(db, "1", "", tenant_id="default")
    assert "Manifiesto homeostasis" in out or "manifiesto" in out.lower()
    assert "/goals" in out


def test_execute_homeostasis_goals_set_infra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_db(tmp_path / "set.duckdb")
    saved: list[HomeostasisManifest] = []

    def _fake_save(**kwargs: Any) -> bool:
        saved.append(kwargs["manifest"])
        return True

    monkeypatch.setattr("harness_core.targets.save_homeostasis_manifest", _fake_save)
    out = execute_homeostasis_goals(db, "5", "--set error_rate_pct 2", tenant_id="t1")
    assert "error_rate_pct" in out
    assert saved and saved[-1].infra.error_rate_pct == 2.0


def test_execute_homeostasis_goals_add_and_rm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_db(tmp_path / "crud.duckdb")
    store = HomeostasisManifest(
        goals=[
            DomainGoal(
                belief_key="completion_rate_pct",
                target_value=95.0,
                threshold=2.0,
                title="Completion rate",
            )
        ]
    )

    def _fake_save(**kwargs: Any) -> bool:
        nonlocal store
        store = kwargs["manifest"]
        return True

    monkeypatch.setattr("harness_core.targets.save_homeostasis_manifest", _fake_save)
    monkeypatch.setattr(
        "harness_core.targets.load_homeostasis_manifest",
        lambda *_a, **_k: store,
    )
    out_rm = execute_homeostasis_goals(db, "9", "--rm completion_rate_pct", tenant_id="t1")
    assert "eliminada" in out_rm.lower()
    assert store.goals == []


def test_execute_homeostasis_goals_migrate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_db(tmp_path / "mig.duckdb")
    set_manager_goals(
        db,
        "7",
        [
            {
                "belief_key": "latency_ms",
                "target_value": 250.0,
                "threshold": 25.0,
                "title": "Latency budget",
            }
        ],
    )
    captured: dict[str, Any] = {}

    def _fake_save(**kwargs: Any) -> bool:
        captured["manifest"] = kwargs["manifest"]
        return True

    monkeypatch.setattr("harness_core.targets.save_homeostasis_manifest", _fake_save)
    out = execute_homeostasis_goals(db, "7", "--migrate", tenant_id="t1")
    assert "Migradas" in out
    assert captured["manifest"].goals[0].belief_key == "latency_ms"


def _manifest_with_goals() -> HomeostasisManifest:
    return HomeostasisManifest(
        goals=[
            DomainGoal(
                belief_key="completion_rate_pct",
                target_value=95.0,
                threshold=2.0,
                title="Completion rate",
            ),
            DomainGoal(
                belief_key="latency_ms",
                target_value=250.0,
                threshold=25.0,
                title="Latency budget",
            ),
        ]
    )


def _patch_manifest_store(
    monkeypatch: pytest.MonkeyPatch, initial: HomeostasisManifest
) -> list[HomeostasisManifest]:
    store = initial
    saved: list[HomeostasisManifest] = []

    def _fake_save(**kwargs: Any) -> bool:
        nonlocal store
        store = kwargs["manifest"]
        saved.append(store)
        return True

    monkeypatch.setattr("harness_core.targets.save_homeostasis_manifest", _fake_save)
    monkeypatch.setattr(
        "harness_core.targets.load_homeostasis_manifest",
        lambda *_a, **_k: store,
    )
    return saved


def test_execute_homeostasis_goals_rm_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_db(tmp_path / "rm_all.duckdb")
    saved = _patch_manifest_store(monkeypatch, _manifest_with_goals())
    out = execute_homeostasis_goals(db, "10", "rm all", tenant_id="t1")
    assert "eliminadas" in out.lower()
    assert saved and saved[-1].goals == []


def test_execute_homeostasis_goals_rm_by_key_without_dash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_db(tmp_path / "rm_key.duckdb")
    saved = _patch_manifest_store(monkeypatch, _manifest_with_goals())
    out = execute_homeostasis_goals(db, "11", "rm latency_ms", tenant_id="t1")
    assert "eliminada" in out.lower()
    assert saved and len(saved[-1].goals) == 1
    assert saved[-1].goals[0].belief_key == "completion_rate_pct"


def test_execute_homeostasis_goals_rm_by_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_db(tmp_path / "rm_idx.duckdb")
    saved = _patch_manifest_store(monkeypatch, _manifest_with_goals())
    out = execute_homeostasis_goals(db, "12", "rm 1", tenant_id="t1")
    assert "eliminada" in out.lower()
    assert saved and len(saved[-1].goals) == 1
    assert saved[-1].goals[0].belief_key == "latency_ms"


def test_execute_homeostasis_goals_rm_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_db(tmp_path / "rm_unknown.duckdb")
    _patch_manifest_store(monkeypatch, _manifest_with_goals())
    out = execute_homeostasis_goals(db, "13", "rm foobar", tenant_id="t1")
    assert "no encontré" in out.lower()


def test_execute_homeostasis_goals_listing_shows_goal_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_db(tmp_path / "list_ids.duckdb")
    _patch_manifest_store(monkeypatch, _manifest_with_goals())
    out = execute_homeostasis_goals(db, "14", "", tenant_id="t1")
    assert "goal-id:" not in out
    assert "/goals rm all" in out
    assert "**completion_rate_pct**" in out


def test_domain_goal_default_kind_is_task() -> None:
    g = DomainGoal(belief_key="latency_ms", target_value=1.0, threshold=0.1, title="Latency")
    assert g.goal_kind == "task"
    loaded = DomainGoal.model_validate(
        {"belief_key": "x", "target_value": 0.0, "threshold": 0.0, "title": "X"}
    )
    assert loaded.goal_kind == "task"


def test_execute_homeostasis_goals_monitor_and_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_db(tmp_path / "monitor.duckdb")
    saved = _patch_manifest_store(monkeypatch, _manifest_with_goals())
    out_mon = execute_homeostasis_goals(db, "15", "--monitor latency_ms", tenant_id="t1")
    assert "monitor" in out_mon.lower()
    assert saved[-1].goals[1].goal_kind == "monitor"

    out_list = execute_homeostasis_goals(db, "15", "", tenant_id="t1")
    assert "tipo=monitor" in out_list

    out_task = execute_homeostasis_goals(db, "15", "--task latency_ms", tenant_id="t1")
    assert "tarea discreta" in out_task.lower() or "goal_kind=task" in out_task
    assert saved[-1].goals[1].goal_kind == "task"


def test_assess_goals_list_alignment_includes_goal_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.homeostasis.goals_alignment import assess_goals_list_alignment

    goals = [
        {
            "belief_key": "error_rate_pct",
            "target_value": 2.0,
            "threshold": 0.5,
            "title": "Tasa de error baja",
            "observed_value": 5.0,
            "goal_kind": "monitor",
        }
    ]
    report = assess_goals_list_alignment(MagicMock(), "c1", goals, worker_id="w1")
    assert report.items[0].goal_kind == "monitor"


def test_hitl_declarable_blocks_monitor_goals() -> None:
    from duckclaw.homeostasis.goals_alignment import hitl_declarable_for_goals

    ok, note = hitl_declarable_for_goals(
        [{"belief_key": "latency_ms", "goal_kind": "monitor"}]
    )
    assert ok is False
    assert "monitor" in note.lower()
    ok2, _ = hitl_declarable_for_goals([{"belief_key": "task_one", "goal_kind": "task"}])
    assert ok2 is True


def test_execute_homeostasis_goals_priority_order_and_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_db(tmp_path / "prio.duckdb")
    store = HomeostasisManifest(
        goals=[
            DomainGoal(
                belief_key="prueba2",
                target_value=0.0,
                threshold=0.0,
                title="Prueba 2",
                priority=2,
            ),
            DomainGoal(
                belief_key="prueba1",
                target_value=0.0,
                threshold=0.0,
                title="Prueba 1",
                priority=1,
            ),
        ]
    )
    saved = _patch_manifest_store(monkeypatch, store)
    out_list = execute_homeostasis_goals(db, "20", "", tenant_id="t1")
    assert out_list.index("P1") < out_list.index("P2")
    assert out_list.index("**prueba1**") < out_list.index("**prueba2**")

    out_set = execute_homeostasis_goals(db, "20", "--priority prueba2 1", tenant_id="t1")
    assert "P1" in out_set
    assert saved[-1].goals
    prueba2 = next(g for g in saved[-1].goals if g.belief_key == "prueba2")
    assert prueba2.priority == 1


def test_execute_homeostasis_goals_add_assigns_next_priority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _make_db(tmp_path / "prio_add.duckdb")
    store = HomeostasisManifest(
        goals=[
            DomainGoal(
                belief_key="solo",
                target_value=1.0,
                threshold=0.1,
                title="Solo",
                priority=1,
            )
        ]
    )
    saved = _patch_manifest_store(monkeypatch, store)
    out = execute_homeostasis_goals(db, "21", "nueva meta test", tenant_id="t1")
    assert "prioridad P2" in out.lower() or "P2" in out
    added = next(g for g in saved[-1].goals if g.belief_key != "solo")
    assert added.priority == 2


def test_assess_goals_list_alignment_sorted_by_priority() -> None:
    from duckclaw.homeostasis.goals_alignment import assess_goals_list_alignment

    goals = [
        {
            "belief_key": "low",
            "target_value": 1.0,
            "threshold": 0.1,
            "title": "Low",
            "priority": 2,
        },
        {
            "belief_key": "high",
            "target_value": 1.0,
            "threshold": 0.1,
            "title": "High",
            "priority": 1,
        },
    ]
    report = assess_goals_list_alignment(MagicMock(), "c2", goals, worker_id="w1")
    assert report.items[0].belief_key == "high"
    assert report.items[0].priority == 1

