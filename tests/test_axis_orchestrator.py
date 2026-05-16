"""Coordinador ADF (AXIS-Maestro → subagentes)."""

from __future__ import annotations

from duckclaw.workers.orchestrator import (
    effective_delegation_pool,
    load_orchestrator_config,
    pick_delegate_heuristic,
)


def test_load_orchestrator_config_axis_maestro() -> None:
    cfg = load_orchestrator_config("AXIS-Maestro")
    assert cfg is not None
    assert cfg.coordinator_id == "AXIS-Maestro"
    assert "AXIS-Coder" in cfg.orchestrates
    assert "AXIS-Radar" in cfg.orchestrates


def test_load_orchestrator_config_maestro_alias() -> None:
    cfg = load_orchestrator_config("maestro")
    assert cfg is not None
    assert cfg.coordinator_id == "AXIS-Maestro"


def test_effective_delegation_pool_intersects_team() -> None:
    cfg = load_orchestrator_config("AXIS-Maestro")
    assert cfg is not None
    pool = effective_delegation_pool(
        cfg.orchestrates,
        ["AXIS-Coder", "AXIS-Radar", "finanz"],
    )
    assert pool == ["AXIS-Coder", "AXIS-Radar"]


def test_pick_delegate_heuristic_cve_to_radar() -> None:
    pool = ["AXIS-Maestro", "AXIS-Coder", "AXIS-Radar"]
    assert (
        pick_delegate_heuristic(
            "¿Hay CVE nuevos para OpenSSH?",
            pool,
            coordinator_id="AXIS-Maestro",
        )
        == "AXIS-Radar"
    )
