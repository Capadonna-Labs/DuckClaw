"""Tests for homeostasis (Active Inference Framework)."""

from __future__ import annotations

import json

import duckclaw
import pytest

from duckclaw.homeostasis import (
    BeliefRegistry,
    compute_surprise,
    load_beliefs_from_config,
    SurpriseCalculator,
)
from duckclaw.homeostasis.surprise import SurpriseResult


def test_compute_surprise_no_anomaly() -> None:
    """Delta within threshold -> no anomaly."""
    r = compute_surprise(observed=0.88, target=0.90, threshold=0.05)
    assert isinstance(r, SurpriseResult)
    assert r.delta == pytest.approx(0.02)
    assert r.is_anomaly is False
    assert r.target == 0.90
    assert r.observed == 0.88


def test_compute_surprise_anomaly() -> None:
    """Delta exceeds threshold -> anomaly."""
    r = compute_surprise(observed=0.80, target=0.90, threshold=0.05)
    assert r.delta == pytest.approx(0.10)
    assert r.is_anomaly is True


def test_compute_surprise_ceiling_maintain() -> None:
    """ceiling: observed bajo el techo + banda -> no anomalía."""
    r = compute_surprise(observed=0.04, target=0.05, threshold=0.01, comparison="ceiling")
    assert r.is_anomaly is False
    assert r.delta == pytest.approx(0.0)


def test_compute_surprise_ceiling_anomaly() -> None:
    """ceiling: observed > target + threshold -> anomalía."""
    r = compute_surprise(observed=0.07, target=0.05, threshold=0.01, comparison="ceiling")
    assert r.is_anomaly is True
    assert r.delta == pytest.approx(0.02)


def test_compute_surprise_exact_threshold() -> None:
    """Delta equals threshold -> no anomaly (strict >). Use exact values to avoid float precision."""
    r = compute_surprise(observed=5.0, target=10.0, threshold=5.0)
    assert r.delta == 5.0
    assert r.is_anomaly is False


def test_surprise_calculator_compute() -> None:
    """SurpriseCalculator.compute is alias for compute_surprise."""
    r = SurpriseCalculator.compute(5.0, 5.0, 1.0)
    assert r.delta == 0.0
    assert r.is_anomaly is False


def test_load_beliefs_from_config_empty() -> None:
    """Empty or None config returns empty lists."""
    beliefs, actions = load_beliefs_from_config(None)
    assert beliefs == []
    assert actions == {}

    beliefs, actions = load_beliefs_from_config({})
    assert beliefs == []
    assert actions == {}


def test_load_beliefs_ceiling_comparison() -> None:
    """YAML puede declarar comparison: ceiling."""
    config = {
        "beliefs": [{"key": "latency_ms", "target": 250.0, "threshold": 25.0, "comparison": "ceiling"}],
        "actions": [],
    }
    beliefs, _ = load_beliefs_from_config(config)
    assert len(beliefs) == 1
    assert beliefs[0].comparison == "ceiling"


def test_load_beliefs_from_config_valid() -> None:
    """Valid config parses beliefs and actions."""
    config = {
        "beliefs": [
            {"key": "test_coverage", "target": 0.90, "threshold": 0.05},
            {"key": "latency_ms", "target": 5000.0, "threshold": 500.0},
        ],
        "actions": [
            {"trigger": "test_coverage_drop", "skill": "github_create_issue", "message": "Cobertura baja."},
        ],
    }
    beliefs, actions = load_beliefs_from_config(config)
    assert len(beliefs) == 2
    assert beliefs[0].key == "test_coverage"
    assert beliefs[0].target == 0.90
    assert beliefs[0].threshold == 0.05
    assert len(actions) == 1
    assert "test_coverage_drop" in actions
    assert actions["test_coverage_drop"].skill == "github_create_issue"


def test_belief_registry_from_config() -> None:
    """BeliefRegistry.from_config creates registry."""
    config = {"beliefs": [{"key": "x", "target": 1.0, "threshold": 0.1}], "actions": []}
    reg = BeliefRegistry.from_config(config)
    assert reg.get_belief("x") is not None
    assert reg.get_belief("x").target == 1.0
    assert reg.get_belief("y") is None


def test_belief_registry_trigger_for_belief() -> None:
    """trigger_for_belief generates expected trigger names."""
    reg = BeliefRegistry.from_config({"beliefs": [], "actions": []})
    assert reg.trigger_for_belief("test_coverage", is_drop=True) == "test_coverage_drop"
    assert reg.trigger_for_belief("test_coverage", is_drop=False) == "test_coverage_breach"


def test_homeostasis_manager_maintain() -> None:
    """HomeostasisManager.check returns maintain when within threshold."""
    db = duckclaw.DuckClaw(":memory:")
    db.execute("CREATE SCHEMA IF NOT EXISTS test_worker")
    db.execute("""
        CREATE TABLE IF NOT EXISTS test_worker.agent_beliefs (
            belief_key VARCHAR PRIMARY KEY,
            target_value REAL NOT NULL,
            observed_value REAL,
            threshold REAL NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    config = {"beliefs": [{"key": "completion_rate_pct", "target": 95.0, "threshold": 2.0}], "actions": []}
    from duckclaw.homeostasis import HomeostasisManager

    reg = BeliefRegistry.from_config(config)
    mgr = HomeostasisManager(db=db, schema="test_worker", registry=reg)
    plan = mgr.check("completion_rate_pct", 94.0, auto_update=True)
    assert plan["action"] == "maintain"
    assert "completion_rate_pct" in plan["belief_key"]


def test_homeostasis_manager_restore() -> None:
    """HomeostasisManager.check returns restore when anomaly."""
    db = duckclaw.DuckClaw(":memory:")
    db.execute("CREATE SCHEMA IF NOT EXISTS test_worker2")
    db.execute("""
        CREATE TABLE IF NOT EXISTS test_worker2.agent_beliefs (
            belief_key VARCHAR PRIMARY KEY,
            target_value REAL NOT NULL,
            observed_value REAL,
            threshold REAL NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    config = {
        "beliefs": [{"key": "completion_rate_pct", "target": 95.0, "threshold": 2.0}],
        "actions": [{"trigger": "completion_rate_pct_drop", "skill": "get_summary", "message": "Desviación."}],
    }
    from duckclaw.homeostasis import HomeostasisManager

    reg = BeliefRegistry.from_config(config)
    mgr = HomeostasisManager(db=db, schema="test_worker2", registry=reg)
    plan = mgr.check("completion_rate_pct", 80.0, auto_update=True)
    assert plan["action"] == "restore"
    assert plan["skill_to_invoke"] == "get_summary"
    assert "Desviación" in plan["message"]


def test_homeostasis_manager_ceiling_restore() -> None:
    """HomeostasisManager con belief ceiling dispara restore cuando una métrica supera techo."""
    db = duckclaw.DuckClaw(":memory:")
    db.execute("CREATE SCHEMA IF NOT EXISTS test_worker_ceiling")
    db.execute("""
        CREATE TABLE IF NOT EXISTS test_worker_ceiling.agent_beliefs (
            belief_key VARCHAR PRIMARY KEY,
            target_value REAL NOT NULL,
            observed_value REAL,
            threshold REAL NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    config = {
        "beliefs": [{"key": "latency_ms", "target": 250.0, "threshold": 25.0, "comparison": "ceiling"}],
        "actions": [{"trigger": "latency_ms_breach", "skill": "x", "message": "Latencia alta."}],
    }
    from duckclaw.homeostasis import HomeostasisManager

    reg = BeliefRegistry.from_config(config)
    mgr = HomeostasisManager(db=db, schema="test_worker_ceiling", registry=reg)
    plan = mgr.check("latency_ms", 400.0, auto_update=True)
    assert plan["action"] == "restore"


def test_homeostasis_manager_unknown_belief() -> None:
    """HomeostasisManager.check returns unknown for undefined belief."""
    db = duckclaw.DuckClaw(":memory:")
    db.execute("CREATE SCHEMA IF NOT EXISTS test_worker3")
    db.execute("""
        CREATE TABLE IF NOT EXISTS test_worker3.agent_beliefs (
            belief_key VARCHAR PRIMARY KEY,
            target_value REAL NOT NULL,
            observed_value REAL,
            threshold REAL NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    from duckclaw.homeostasis import HomeostasisManager

    reg = BeliefRegistry.from_config({"beliefs": [], "actions": []})
    mgr = HomeostasisManager(db=db, schema="test_worker3", registry=reg)
    plan = mgr.check("unknown_key", 1.0, auto_update=False)
    assert plan["action"] == "unknown"
    assert "no definida" in plan["message"]


def test_register_homeostasis_skill_no_config() -> None:
    """register_homeostasis_skill does nothing when spec has no homeostasis_config."""
    from duckclaw.forge.skills.homeostasis_bridge import register_homeostasis_skill

    tools = []
    spec = type("Spec", (), {"homeostasis_config": None, "schema_name": "test"})()
    db = duckclaw.DuckClaw(":memory:")
    register_homeostasis_skill(tools, spec, db)
    assert len(tools) == 0


def test_register_homeostasis_skill_with_config() -> None:
    """register_homeostasis_skill adds homeostasis_check + assess_crons_alignment when config present."""
    from duckclaw.forge.skills.homeostasis_bridge import register_homeostasis_skill

    db = duckclaw.DuckClaw(":memory:")
    db.execute("CREATE SCHEMA IF NOT EXISTS analytics_worker")
    db.execute("""
        CREATE TABLE IF NOT EXISTS analytics_worker.agent_beliefs (
            belief_key VARCHAR PRIMARY KEY,
            target_value REAL NOT NULL,
            observed_value REAL,
            threshold REAL NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    spec = type("Spec", (), {
        "homeostasis_config": {
            "beliefs": [{"key": "completion_rate_pct", "target": 95.0, "threshold": 2.0}],
            "actions": [],
        },
        "schema_name": "analytics_worker",
    })()
    tools = []
    register_homeostasis_skill(tools, spec, db)
    names = {t.name for t in tools}
    assert names == {
        "homeostasis_check",
        "assess_crons_alignment",
        "manage_homeostasis_goals",
    }
    hc = next(t for t in tools if t.name == "homeostasis_check")
    result = hc.invoke({"belief_key": "completion_rate_pct", "observed_value": 94.0})
    plan = json.loads(result)
    assert plan["action"] == "maintain"


def test_manage_homeostasis_goals_reuses_bound_worker_db_on_write() -> None:
    """Writes must not open a second DuckClaw on the same vault path in-process."""
    from unittest.mock import MagicMock, patch

    from duckclaw.forge.skills.homeostasis_bridge import register_homeostasis_skill

    vault = "/tmp/worker_goals.duckdb"
    bound = MagicMock()
    bound._path = vault
    bound._read_only = False

    spec = type("Spec", (), {
        "homeostasis_config": {
            "beliefs": [{"key": "completion_rate_pct", "target": 95.0, "threshold": 2.0}],
            "actions": [],
        },
        "schema_name": "agent_worker",
    })()
    tools: list = []

    with patch(
        "duckclaw.forge.skills.goals_tool_context.get_goals_tool_chat_id",
        return_value="chat-1",
    ):
        with patch(
            "duckclaw.forge.skills.goals_tool_context.get_goals_tool_db_path",
            return_value=vault,
        ):
            with patch(
                "duckclaw.forge.skills.goals_tool_context.get_goals_tool_tenant_id",
                return_value="default",
            ):
                with patch("duckclaw.DuckClaw") as duck_ctor:
                    with patch(
                        "duckclaw.commands.goals.execute_homeostasis_goals",
                        return_value="ok",
                    ) as exec_goals:
                        register_homeostasis_skill(tools, spec, bound)
                        mgr = next(t for t in tools if t.name == "manage_homeostasis_goals")
                        raw = mgr.invoke({"command": "rm all"})

    duck_ctor.assert_not_called()
    exec_goals.assert_called_once()
    assert exec_goals.call_args[0][0] is bound
    payload = json.loads(raw)
    assert payload["status"] == "ok"


def test_loader_ensures_agent_beliefs() -> None:
    """run_schema creates agent_beliefs table in worker schema."""
    from duckclaw.workers.loader import run_schema
    from duckclaw.workers.manifest import WorkerSpec
    from pathlib import Path

    db = duckclaw.DuckClaw(":memory:")
    spec = WorkerSpec(
        worker_id="test",
        logical_worker_id="test",
        name="Test",
        schema_name="test_schema",
        llm_required=None,
        temperature=0.2,
        topology="general",
        skills_list=[],
        allowed_tables=[],
        read_only=False,
        worker_dir=Path("."),
        homeostasis_config=None,
    )
    run_schema(db, spec)
    r = db.query("SELECT * FROM test_schema.agent_beliefs LIMIT 1")
    rows = json.loads(r) if isinstance(r, str) else (r or [])
    assert rows is not None
