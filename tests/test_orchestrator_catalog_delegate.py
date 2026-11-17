"""A catalog coordinator (no template dir) still configures and picks its delegate."""

from __future__ import annotations

from duckclaw.workers import orchestrator as orch


def test_planner_delegate_matches_catalog_id_ignoring_punctuation() -> None:
    assert orch.pick_delegate_from_planner("quant_trader", ["quant-trader", "quant_analyst"]) == "quant-trader"
    assert orch.pick_delegate_from_planner("nadie", ["quant-trader"]) is None


def test_catalog_manifest_enables_orchestrator(monkeypatch) -> None:
    manifest = {"orchestrator": {"enabled": True, "orchestrates": ["quant_trader", "quant_reporter"]}}
    monkeypatch.setattr(orch, "catalog_manifest_and_files", lambda db, w, t: ("quant_analyst", manifest, {}))
    cfg = orch.load_orchestrator_config("quant_analyst", db=object(), tenant_id="t1")
    assert cfg is not None and cfg.coordinator_id == "quant_analyst"
    assert set(cfg.orchestrates) == {"quant_trader", "quant_reporter"}
    assert orch.load_orchestrator_config("quant_analyst") is None   # no db, no template dir: unchanged
