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
