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
    assert sidecar.os.environ.get("DUCKCLAW_ADMIN_API_KEY")


def test_apply_desktop_env_respects_preset_db_path(monkeypatch, tmp_path) -> None:
    sidecar = _load_sidecar_main()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    custom_db = tmp_path / "isolated" / "smoke.duckdb"
    custom_db.parent.mkdir(parents=True)
    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", str(custom_db))
    repo = Path(__file__).resolve().parents[1]
    sidecar.apply_desktop_env(repo_root=repo)
    assert sidecar.os.environ.get("DUCKCLAW_GATEWAY_DB_PATH") == str(custom_db)


def test_load_or_create_desktop_env_is_stable(monkeypatch, tmp_path) -> None:
    sidecar = _load_sidecar_main()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    first = sidecar.load_or_create_desktop_env()
    assert first["DUCKCLAW_ADMIN_API_KEY"]
    assert first["DUCKCLAW_ADMIN_EMAIL"] == "admin@duckclaw.local"
    assert first["DUCKCLAW_ADMIN_PASSWORD"] == first["DUCKCLAW_DESKTOP_ADMIN_PASSWORD"]
    second = sidecar.load_or_create_desktop_env()
    assert second["DUCKCLAW_ADMIN_API_KEY"] == first["DUCKCLAW_ADMIN_API_KEY"]
    assert (tmp_path / "DuckClaw" / "desktop.env").is_file()


def test_apply_desktop_env_file_overwrites_stale_admin_key(monkeypatch, tmp_path) -> None:
    sidecar = _load_sidecar_main()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("DUCKCLAW_ADMIN_API_KEY", "stale-process-key")
    env_path = tmp_path / "DuckClaw" / "desktop.env"
    env_path.parent.mkdir(parents=True)
    env_path.write_text("DUCKCLAW_ADMIN_API_KEY=desktop-authoritative-key\n", encoding="utf-8")
    sidecar.apply_desktop_env_file()
    assert sidecar.os.environ["DUCKCLAW_ADMIN_API_KEY"] == "desktop-authoritative-key"
