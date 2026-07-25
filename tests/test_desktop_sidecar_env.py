"""Desktop sidecar composition root helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_sidecar_main():
    spec = importlib.util.spec_from_file_location(
        "desktop_sidecar_main",
        Path(__file__).resolve().parents[1] / "services" / "desktop-sidecar" / "run.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_desktop_data_dir_uses_localappdata(monkeypatch, tmp_path) -> None:
    sidecar = _load_sidecar_main()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    data = sidecar.desktop_data_dir()
    assert data == tmp_path / "DuckClaw"


def test_apply_desktop_env_sets_lite_and_db_path(monkeypatch, tmp_path) -> None:
    sidecar = _load_sidecar_main()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    repo = Path(__file__).resolve().parents[1]
    data = sidecar.apply_desktop_env(repo_root=repo)

    assert data == tmp_path / "DuckClaw"
    assert sidecar.os.environ.get("LITE_MODE") == "1"
    assert sidecar.os.environ.get("DUCKCLAW_SPAWN_PROFILE") == "1"
    assert "duckclaw.duckdb" in sidecar.os.environ.get("DUCKCLAW_GATEWAY_DB_PATH", "")
