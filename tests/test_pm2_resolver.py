from __future__ import annotations

from pathlib import Path

import pytest


def test_resolve_pm2_executable_prefers_cmd_on_windows(monkeypatch, tmp_path: Path) -> None:
    from duckclaw.ops.toolchain import pm2_argv, resolve_pm2_executable

    npm_dir = tmp_path / "npm"
    npm_dir.mkdir()
    shim = npm_dir / "pm2"
    shim.write_text("@echo off\n", encoding="utf-8")
    cmd = npm_dir / "pm2.cmd"
    cmd.write_text("@echo pm2\n", encoding="utf-8")

    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("duckclaw.ops.toolchain.platform.system", lambda: "Windows")
    monkeypatch.setattr("duckclaw.ops.toolchain.shutil.which", lambda _name: None)

    resolved = resolve_pm2_executable()
    assert resolved == str(cmd)
    assert pm2_argv("jlist") == [str(cmd), "jlist"]


def test_resolve_pm2_executable_unix_uses_which(monkeypatch) -> None:
    from duckclaw.ops.toolchain import resolve_pm2_executable

    monkeypatch.setattr("duckclaw.ops.toolchain.platform.system", lambda: "Linux")
    monkeypatch.setattr(
        "duckclaw.ops.toolchain.shutil.which",
        lambda name: "/usr/bin/pm2" if name == "pm2" else None,
    )

    assert resolve_pm2_executable() == "/usr/bin/pm2"
