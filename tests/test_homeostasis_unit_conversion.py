"""Unit tests for generic homeostasis observed-value conversion."""

from __future__ import annotations

import pytest

from duckclaw.homeostasis.unit_conversion import (
    build_settings_lookup,
    needs_pct_conversion,
    normalize_observed,
    try_normalize_goal_observed,
)


def test_normalize_observed_pct_with_generic_anchor() -> None:
    lookup = {"test_anchor": 907_056.0}
    assert normalize_observed(
        -18_141.0,
        target_unit="pct",
        anchor_setting_key="test_anchor",
        settings_lookup=lookup,
    ) == pytest.approx(-2.0, rel=1e-4)


def test_normalize_observed_pct_different_anchor_changes_result() -> None:
    raw = -18_141.0
    pct_a = normalize_observed(
        raw,
        target_unit="pct",
        anchor_setting_key="test_anchor",
        settings_lookup={"test_anchor": 907_056.0},
    )
    pct_b = normalize_observed(
        raw,
        target_unit="pct",
        anchor_setting_key="test_anchor",
        settings_lookup={"test_anchor": 500_000.0},
    )
    assert pct_a != pct_b
    assert pct_a == pytest.approx(-2.0, rel=1e-4)
    assert pct_b == pytest.approx(-3.6282, rel=1e-3)


def test_normalize_observed_usd_no_conversion() -> None:
    assert (
        normalize_observed(
            1234.56,
            target_unit="usd",
            anchor_setting_key=None,
            settings_lookup={},
        )
        == 1234.56
    )


def test_normalize_observed_raw_no_conversion() -> None:
    assert (
        normalize_observed(
            99.0,
            target_unit="raw",
            anchor_setting_key=None,
            settings_lookup={},
        )
        == 99.0
    )


def test_normalize_observed_pct_requires_anchor_key() -> None:
    with pytest.raises(ValueError, match="anchor_setting_key"):
        normalize_observed(
            100.0,
            target_unit="pct",
            anchor_setting_key="",
            settings_lookup={"test_anchor": 1000.0},
        )


def test_normalize_observed_pct_requires_valid_anchor_value() -> None:
    with pytest.raises(ValueError, match="valid numeric anchor"):
        normalize_observed(
            100.0,
            target_unit="pct",
            anchor_setting_key="missing_key",
            settings_lookup={},
        )


def test_needs_pct_conversion_detects_absolute_vs_percent_target() -> None:
    assert needs_pct_conversion(-3993.59, 2.0, 0.5) is True
    assert needs_pct_conversion(0.42, 2.0, 0.5) is False


def test_try_normalize_goal_observed_converts_on_mismatch_only() -> None:
    goal = {
        "belief_key": "metric_limit",
        "target_value": 2.0,
        "threshold": 0.5,
        "target_unit": "pct",
        "anchor_setting_key": "test_anchor",
        "observed_value": -3993.59,
    }
    lookup = {"test_anchor": 907_056.0}
    normalized = try_normalize_goal_observed(
        goal,
        settings_lookup=lookup,
        target=2.0,
        threshold=0.5,
    )
    assert normalized == pytest.approx(-0.4403, rel=1e-3)

    goal_already_pct = dict(goal, observed_value=0.42)
    assert (
        try_normalize_goal_observed(
            goal_already_pct,
            settings_lookup=lookup,
            target=2.0,
            threshold=0.5,
        )
        == 0.42
    )


def test_patch_goal_units_in_manifest_idempotent() -> None:
    from duckclaw.commands.goals import patch_goal_units_in_manifest
    from harness_core.states.loop_state import DomainGoal, HomeostasisManifest

    manifest = HomeostasisManifest(
        goals=[
            DomainGoal(
                belief_key="metric_pct_limit",
                target_value=2.0,
                threshold=0.5,
                anchor_setting_key="test_anchor",
                observed_value=-3993.59,
                goal_kind="monitor",
            )
        ]
    )
    updated, patched = patch_goal_units_in_manifest(manifest)
    assert patched == ["metric_pct_limit"]
    goal = updated.goals[0]
    assert goal.target_unit == "pct"
    assert goal.anchor_setting_key == "test_anchor"
    assert goal.observed_value is None
    again, patched_again = patch_goal_units_in_manifest(updated)
    assert patched_again == []


def test_build_settings_lookup_reads_session_settings(tmp_path) -> None:
    import duckdb

    from duckclaw import DuckClaw
    from duckclaw.admin_runtime_settings import ensure_admin_runtime_settings_table
    from duckclaw.runtime_session_settings import upsert_session_runtime_setting

    db_path = tmp_path / "settings.duckdb"
    duckdb.connect(str(db_path)).close()
    db = DuckClaw(str(db_path))
    ensure_admin_runtime_settings_table(db)
    upsert_session_runtime_setting(
        db,
        "chat-1",
        "test_anchor",
        "907056",
        tenant_id="default",
    )
    lookup = build_settings_lookup(db, "chat-1", "default", ["test_anchor"])
    assert lookup["test_anchor"] == pytest.approx(907_056.0)


def test_assess_goals_list_alignment_converts_pct_with_injected_anchor(tmp_path) -> None:
    import duckdb

    from duckclaw import DuckClaw
    from duckclaw.admin_runtime_settings import ensure_admin_runtime_settings_table
    from duckclaw.homeostasis.goals_alignment import assess_goals_list_alignment
    from duckclaw.runtime_session_settings import upsert_session_runtime_setting

    db_path = tmp_path / "pct-convert.duckdb"
    con = duckdb.connect(str(db_path))
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
    db = DuckClaw(str(db_path))
    ensure_admin_runtime_settings_table(db)
    chat_id = "pct-chat"
    upsert_session_runtime_setting(
        db,
        chat_id,
        "test_anchor",
        "907056",
        tenant_id="default",
    )
    goals = [
        {
            "belief_key": "metric_pct_limit",
            "target_value": 2.0,
            "threshold": 0.5,
            "target_unit": "pct",
            "anchor_setting_key": "test_anchor",
            "observed_value": -3993.59,
            "title": "Metric within percent ceiling",
            "goal_kind": "monitor",
            "priority": 1,
        }
    ]
    report = assess_goals_list_alignment(db, chat_id, goals, worker_id="worker-a")
    assert report.items[0].scale_mismatch is False
    assert report.items[0].has_data is True
    assert report.items[0].observed == pytest.approx(-0.4403, rel=1e-3)
    # Same magnitude scale as target (not thousands vs single-digit percent)
    assert abs(report.items[0].observed or 0) <= (report.items[0].target or 0) + (
        report.items[0].threshold or 0
    )
