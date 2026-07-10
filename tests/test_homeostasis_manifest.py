"""Homeostasis manifest load/save/migrate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from harness_core.states.meditate_state import DomainGoal, HomeostasisManifest, HomeostasisTarget
from harness_core.targets import (
    _parse_targets_json,
    load_homeostasis_manifest,
    load_homeostasis_targets,
    set_infra_field,
)


def _make_db_with_manifest(path: Path, targets_json: Any, tenant_id: str = "default") -> Any:
    from duckclaw import DuckClaw

    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA IF NOT EXISTS main")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS main.homeostasis_targets (
            tenant_id VARCHAR PRIMARY KEY,
            targets_json JSON,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    payload = json.dumps(targets_json) if not isinstance(targets_json, str) else targets_json
    con.execute(
        "INSERT INTO main.homeostasis_targets (tenant_id, targets_json) VALUES (?, ?)",
        [tenant_id, payload],
    )
    con.close()
    return DuckClaw(str(path))


def test_parse_legacy_flat_infra_json() -> None:
    legacy = {"error_rate_pct": 3.0, "stale_tasks_count": 1}
    manifest = _parse_targets_json(legacy)
    assert manifest.infra.error_rate_pct == 3.0
    assert manifest.infra.stale_tasks_count == 1
    assert manifest.goals == []


def test_parse_manifest_wrapper_json() -> None:
    wrapped = {
        "infra": {"error_rate_pct": 1.5},
        "goals": [
            {
                "belief_key": "latency_ms",
                "target_value": 250.0,
                "threshold": 25.0,
                "title": "Latency budget",
            }
        ],
    }
    manifest = _parse_targets_json(wrapped)
    assert manifest.infra.error_rate_pct == 1.5
    assert len(manifest.goals) == 1
    assert manifest.goals[0].belief_key == "latency_ms"


def test_load_homeostasis_targets_compat(tmp_path: Path) -> None:
    db = _make_db_with_manifest(tmp_path / "m.duckdb", {"error_rate_pct": 4.0})
    targets = load_homeostasis_targets(db, "default")
    assert targets.error_rate_pct == 4.0


def test_set_infra_field_rejects_unknown() -> None:
    manifest = HomeostasisManifest()
    try:
        set_infra_field(manifest, "bogus_metric", 1.0)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "bogus_metric" in str(exc)


def test_set_infra_field_ok() -> None:
    manifest = HomeostasisManifest()
    updated = set_infra_field(manifest, "error_rate_pct", 2.5)
    assert updated.infra.error_rate_pct == 2.5


def test_load_manifest_migrate_legacy_goals_from_agent_config(tmp_path: Path) -> None:
    from duckclaw import DuckClaw
    from duckclaw.graphs.on_the_fly_commands import set_manager_goals

    path = tmp_path / "vault.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA IF NOT EXISTS main")
    con.execute(
        """
        CREATE TABLE main.homeostasis_targets (
            tenant_id VARCHAR PRIMARY KEY,
            targets_json JSON,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        "INSERT INTO main.homeostasis_targets (tenant_id, targets_json) VALUES ('t1', '{}')"
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
    db = DuckClaw(str(path))
    set_manager_goals(
        db,
        "42",
        [
            {
                "belief_key": "completion_rate_pct",
                "target_value": 95.0,
                "threshold": 2.0,
                "title": "Completion rate",
            }
        ],
    )
    manifest = load_homeostasis_manifest(db, "t1", chat_id="42", migrate_legacy=True)
    assert len(manifest.goals) == 1
    assert manifest.goals[0].belief_key == "completion_rate_pct"


def test_resolve_homeostasis_tenant_id_prefers_chat_state(tmp_path: Path) -> None:
    from duckclaw import DuckClaw
    from duckclaw.commands.chat_state import set_chat_state
    from harness_core.targets import resolve_homeostasis_tenant_id

    path = tmp_path / "tenant.duckdb"
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
    db = DuckClaw(str(path))
    set_chat_state(db, "chat-1", "goals_proactive_tenant_id", "tenant-from-chat")
    assert resolve_homeostasis_tenant_id(db, "chat-1", "default") == "tenant-from-chat"
    assert resolve_homeostasis_tenant_id(db, "chat-1", None) == "tenant-from-chat"


def test_load_manifest_falls_back_to_harness_core_schema(tmp_path: Path) -> None:
    from duckclaw import DuckClaw

    path = tmp_path / "legacy.duckdb"
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
        "INSERT INTO harness_core.homeostasis_targets (tenant_id, targets_json) VALUES (?, ?)",
        [
            "legacy-tenant",
            json.dumps(
                {
                    "goals": [
                        {
                            "belief_key": "latency_ms",
                            "target_value": 250.0,
                            "threshold": 25.0,
                            "title": "Latency budget",
                        }
                    ]
                }
            ),
        ],
    )
    con.close()
    db = DuckClaw(str(path))
    manifest = load_homeostasis_manifest(db, "legacy-tenant", migrate_legacy=False)
    assert len(manifest.goals) == 1
    assert manifest.goals[0].belief_key == "latency_ms"
