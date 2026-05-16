"""MOC pipeline CLI: fases válidas e inválidas (sin Telegram en tests unitarios)."""

from __future__ import annotations

import sys
from typing import Any

import pytest


@pytest.fixture
def repo_root() -> Any:
    from pathlib import Path

    return Path(__file__).resolve().parent.parent


def _import_moc_pipeline(repo_root: Any) -> Any:
    sys.path.insert(0, str(repo_root))
    agents_src = repo_root / "packages" / "agents" / "src"
    shared_src = repo_root / "packages" / "shared" / "src"
    if str(agents_src) not in sys.path:
        sys.path.insert(0, str(agents_src))
    if str(shared_src) not in sys.path:
        sys.path.insert(0, str(shared_src))
    import scripts.quant.moc_pipeline as mp

    return mp


def test_main_invalid_moc_phase_returns_2(monkeypatch: Any, repo_root: Any, capsys: Any) -> None:
    mp = _import_moc_pipeline(repo_root)
    monkeypatch.setenv("MOC_PHASE", "bogus")
    monkeypatch.setattr(sys, "argv", ["moc_pipeline.py"])
    code = mp.main()
    assert code == 2
    err = capsys.readouterr().err
    assert "calc|remind|expire" in err


def test_main_calc_phase_dispatches_run_calc(monkeypatch: Any, repo_root: Any) -> None:
    mp = _import_moc_pipeline(repo_root)
    seen: list[bool] = []

    def _calc(*, dry_run: bool = False) -> int:
        seen.append(dry_run)
        return 0

    monkeypatch.setenv("MOC_PHASE", "calc")
    monkeypatch.setattr(mp, "run_calc", _calc)
    monkeypatch.setattr(sys, "argv", ["moc_pipeline.py"])
    assert mp.main() == 0
    assert seen == [False]


def test_main_invalid_phase_dry_run_returns_2(monkeypatch: Any, repo_root: Any) -> None:
    mp = _import_moc_pipeline(repo_root)
    monkeypatch.setenv("MOC_PHASE", "bogus")
    monkeypatch.setattr(sys, "argv", ["moc_pipeline.py", "--dry-run"])
    assert mp.main() == 2


def test_main_calc_dry_run_passes_flag(monkeypatch: Any, repo_root: Any) -> None:
    mp = _import_moc_pipeline(repo_root)
    seen: list[bool] = []

    def _calc(*, dry_run: bool = False) -> int:
        seen.append(dry_run)
        return 0

    monkeypatch.setenv("MOC_PHASE", "calc")
    monkeypatch.setattr(mp, "run_calc", _calc)
    monkeypatch.setattr(sys, "argv", ["moc_pipeline.py", "--dry-run"])
    assert mp.main() == 0
    assert seen == [True]
