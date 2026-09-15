"""owner_worker_id separation for /goals."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from duckclaw.commands import goals as goals_mod
from harness_core.states.loop_state import DomainGoal, HomeostasisManifest
from harness_core.targets import filter_goals_for_worker, goal_visible_to_worker
import harness_core.targets as targets_mod


def test_filter_goals_for_worker_shared_and_owned() -> None:
    goals = [
        {"belief_key": "shared", "owner_worker_id": ""},
        {"belief_key": "a", "owner_worker_id": "quant"},
        {"belief_key": "b", "owner_worker_id": "research"},
    ]
    assert [g["belief_key"] for g in filter_goals_for_worker(goals, "quant")] == [
        "shared",
        "a",
    ]
    assert [
        g["belief_key"]
        for g in filter_goals_for_worker(goals, "quant", include_shared=False)
    ] == ["a"]
    assert goal_visible_to_worker(goals[0], "quant")
    assert not goal_visible_to_worker(goals[2], "quant")
    assert goal_visible_to_worker(goals[1], "")


def test_execute_goals_worker_add_list_and_owner(monkeypatch: Any) -> None:
    store = {
        "m": HomeostasisManifest(
            goals=[
                DomainGoal(
                    belief_key="shared_metric",
                    target_value=1.0,
                    threshold=0.1,
                    title="Shared",
                    priority=1,
                )
            ]
        )
    }
    saved: list[HomeostasisManifest] = []

    def _load(*_a: Any, **_k: Any) -> HomeostasisManifest:
        return store["m"]

    def _persist(
        _db: Any, _chat: Any, _tid: str, manifest: HomeostasisManifest, **_k: Any
    ) -> tuple[bool, str]:
        store["m"] = manifest
        saved.append(manifest)
        return True, ""

    monkeypatch.setattr(targets_mod, "load_homeostasis_manifest", _load)
    monkeypatch.setattr(goals_mod, "_persist_homeostasis_manifest_db", _persist)
    monkeypatch.setattr(goals_mod, "_get_goals_registry_for_chat", lambda *_a, **_k: None)
    monkeypatch.setattr(
        goals_mod, "_try_sync_write_homeostasis_manifest", lambda *_a, **_k: False
    )

    db = MagicMock()
    out_add = goals_mod.execute_homeostasis_goals(
        db, "1", "--worker quant max drawdown bajo", tenant_id="t1"
    )
    assert "quant" in out_add
    assert saved
    owned = [g for g in saved[-1].goals if g.belief_key != "shared_metric"]
    assert owned and owned[0].owner_worker_id == "quant"

    out_list = goals_mod.execute_homeostasis_goals(db, "1", "--worker quant", tenant_id="t1")
    assert "worker=`quant`" in out_list or "worker `quant`" in out_list
    assert "shared_metric" not in out_list
    assert "compartida" in out_list.lower() or "+1" in out_list

    out_own = goals_mod.execute_homeostasis_goals(
        db, "1", "--owner shared_metric research", tenant_id="t1"
    )
    assert "research" in out_own
    shared = next(g for g in store["m"].goals if g.belief_key == "shared_metric")
    assert shared.owner_worker_id == "research"

    out_clear = goals_mod.execute_homeostasis_goals(
        db, "1", "--owner shared_metric -", tenant_id="t1"
    )
    assert "compartido" in out_clear.lower() or "sin worker" in out_clear.lower()
    shared = next(g for g in store["m"].goals if g.belief_key == "shared_metric")
    assert shared.owner_worker_id == ""


def test_assess_alignment_filters_by_owner(monkeypatch: Any) -> None:
    from duckclaw.homeostasis.goals_alignment import assess_goals_list_alignment

    monkeypatch.setattr(
        "duckclaw.homeostasis.goals_alignment.refresh_goals_list_observations",
        lambda _db, _chat, _wid, goals, **_k: goals,
    )
    monkeypatch.setattr(
        "duckclaw.commands.goals._get_goals_registry_for_chat",
        lambda *_a, **_k: None,
    )
    goals = [
        {
            "belief_key": "other",
            "target_value": 1.0,
            "threshold": 0.1,
            "title": "Other",
            "priority": 1,
            "owner_worker_id": "research",
            "observed_value": 1.0,
        },
        {
            "belief_key": "mine",
            "target_value": 1.0,
            "threshold": 0.1,
            "title": "Mine",
            "priority": 2,
            "owner_worker_id": "quant",
            "observed_value": 1.0,
        },
        {
            "belief_key": "shared",
            "target_value": 1.0,
            "threshold": 0.1,
            "title": "Shared",
            "priority": 3,
            "owner_worker_id": "",
            "observed_value": 1.0,
        },
    ]
    report = assess_goals_list_alignment(MagicMock(), "c1", goals, worker_id="quant")
    keys = [i.belief_key for i in report.items]
    assert "mine" in keys
    assert "shared" in keys
    assert "other" not in keys
