"""MOC pipeline: Telegram notify on config error, invalid phase, and unhandled exceptions."""

from __future__ import annotations

import os
from typing import Any

import pytest


@pytest.fixture
def repo_root() -> Any:
    from pathlib import Path

    return Path(__file__).resolve().parent.parent


def test_main_invalid_moc_phase_calls_notify(monkeypatch: Any, repo_root: Any) -> None:
    import sys

    sys.path.insert(0, str(repo_root))
    if str(repo_root / "packages" / "agents" / "src") not in sys.path:
        sys.path.insert(0, str(repo_root / "packages" / "agents" / "src"))
    if str(repo_root / "packages" / "shared" / "src") not in sys.path:
        sys.path.insert(0, str(repo_root / "packages" / "shared" / "src"))

    import scripts.quant.moc_pipeline as mp

    calls: list[tuple[str, str, bool]] = []

    def _rec(phase: str, detail: str, *, dry_run: bool) -> None:
        calls.append((phase, detail, dry_run))

    monkeypatch.setenv("MOC_PHASE", "bogus")
    monkeypatch.setattr(mp, "_moc_notify_telegram_safe", _rec)
    monkeypatch.setattr(sys, "argv", ["moc_pipeline.py"])

    code = mp.main()
    assert code == 2
    assert len(calls) == 1
    assert calls[0][0] == "bogus"
    assert "MOC_PHASE inválido" in calls[0][1]
    assert calls[0][2] is False


def test_main_unhandled_exception_notifies_and_returns_1(monkeypatch: Any, repo_root: Any) -> None:
    import sys

    sys.path.insert(0, str(repo_root))
    if str(repo_root / "packages" / "agents" / "src") not in sys.path:
        sys.path.insert(0, str(repo_root / "packages" / "agents" / "src"))
    if str(repo_root / "packages" / "shared" / "src") not in sys.path:
        sys.path.insert(0, str(repo_root / "packages" / "shared" / "src"))

    import scripts.quant.moc_pipeline as mp

    calls: list[tuple[str, str, bool]] = []

    def _rec(phase: str, detail: str, *, dry_run: bool) -> None:
        calls.append((phase, detail, dry_run))

    def _boom(*, dry_run: bool = False) -> int:
        raise RuntimeError("simulated_moc_failure")

    monkeypatch.setenv("MOC_PHASE", "calc")
    monkeypatch.setattr(mp, "run_calc", _boom)
    monkeypatch.setattr(mp, "_moc_notify_telegram_safe", _rec)
    monkeypatch.setattr(sys, "argv", ["moc_pipeline.py"])

    code = mp.main()
    assert code == 1
    assert len(calls) == 1
    assert calls[0][0] == "calc"
    assert "RuntimeError" in calls[0][1]
    assert "simulated_moc_failure" in calls[0][1]


def test_main_invalid_phase_dry_run_skips_notify(monkeypatch: Any, repo_root: Any) -> None:
    import sys

    sys.path.insert(0, str(repo_root))
    if str(repo_root / "packages" / "agents" / "src") not in sys.path:
        sys.path.insert(0, str(repo_root / "packages" / "agents" / "src"))
    if str(repo_root / "packages" / "shared" / "src") not in sys.path:
        sys.path.insert(0, str(repo_root / "packages" / "shared" / "src"))

    import scripts.quant.moc_pipeline as mp

    calls: list[tuple[str, str, bool]] = []

    def _rec(phase: str, detail: str, *, dry_run: bool) -> None:
        calls.append((phase, detail, dry_run))

    monkeypatch.setenv("MOC_PHASE", "bogus")
    monkeypatch.setattr(mp, "_moc_notify_telegram_safe", _rec)
    monkeypatch.setattr(sys, "argv", ["moc_pipeline.py", "--dry-run"])

    code = mp.main()
    assert code == 2
    assert calls == []


def test_moc_calc_enable_batch_auto_exec_default_on(monkeypatch: Any, repo_root: Any) -> None:
    import sys

    sys.path.insert(0, str(repo_root))
    if str(repo_root / "packages" / "agents" / "src") not in sys.path:
        sys.path.insert(0, str(repo_root / "packages" / "agents" / "src"))
    if str(repo_root / "packages" / "shared" / "src") not in sys.path:
        sys.path.insert(0, str(repo_root / "packages" / "shared" / "src"))

    import scripts.quant.moc_pipeline as mp

    monkeypatch.delenv("DUCKCLAW_MOC_PIPELINE_AUTO_EXECUTE", raising=False)
    monkeypatch.delenv("DUCKCLAW_MOC_BATCH_AUTO_EXECUTE", raising=False)
    monkeypatch.delenv("DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS", raising=False)
    mp._moc_calc_enable_batch_auto_execute_env(dry_run=False)
    assert os.environ.get("DUCKCLAW_MOC_BATCH_AUTO_EXECUTE") == "1"
    assert os.environ.get("DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS") == "1"


def test_moc_calc_enable_batch_auto_exec_dry_run_noop(monkeypatch: Any, repo_root: Any) -> None:
    import sys

    sys.path.insert(0, str(repo_root))
    if str(repo_root / "packages" / "agents" / "src") not in sys.path:
        sys.path.insert(0, str(repo_root / "packages" / "agents" / "src"))
    if str(repo_root / "packages" / "shared" / "src") not in sys.path:
        sys.path.insert(0, str(repo_root / "packages" / "shared" / "src"))

    import scripts.quant.moc_pipeline as mp

    monkeypatch.delenv("DUCKCLAW_MOC_BATCH_AUTO_EXECUTE", raising=False)
    mp._moc_calc_enable_batch_auto_execute_env(dry_run=True)
    assert os.environ.get("DUCKCLAW_MOC_BATCH_AUTO_EXECUTE") is None


def test_moc_calc_enable_batch_auto_exec_opt_out(monkeypatch: Any, repo_root: Any) -> None:
    import sys

    sys.path.insert(0, str(repo_root))
    if str(repo_root / "packages" / "agents" / "src") not in sys.path:
        sys.path.insert(0, str(repo_root / "packages" / "agents" / "src"))
    if str(repo_root / "packages" / "shared" / "src") not in sys.path:
        sys.path.insert(0, str(repo_root / "packages" / "shared" / "src"))

    import scripts.quant.moc_pipeline as mp

    monkeypatch.setenv("DUCKCLAW_MOC_PIPELINE_AUTO_EXECUTE", "0")
    monkeypatch.delenv("DUCKCLAW_MOC_BATCH_AUTO_EXECUTE", raising=False)
    monkeypatch.delenv("DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS", raising=False)
    mp._moc_calc_enable_batch_auto_execute_env(dry_run=False)
    assert os.environ.get("DUCKCLAW_MOC_BATCH_AUTO_EXECUTE") is None
    assert os.environ.get("DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS") is None
