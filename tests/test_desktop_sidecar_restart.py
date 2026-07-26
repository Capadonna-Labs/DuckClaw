"""Desktop sidecar restart helper."""

from __future__ import annotations


def test_desktop_backend_exe_path_under_localappdata(monkeypatch, tmp_path) -> None:
    from duckclaw.desktop_sidecar_restart import desktop_backend_exe

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert desktop_backend_exe() == tmp_path / "DuckClaw" / "duckclaw_backend.exe"
