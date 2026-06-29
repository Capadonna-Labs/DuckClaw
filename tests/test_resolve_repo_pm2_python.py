"""resolve_repo_pm2_python: PM2 debe usar el venv del repo si existe."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from duckclaw.ops.manager import resolve_repo_pm2_python


def test_resolve_repo_pm2_python_prefers_dot_venv(monkeypatch, tmp_path: Path) -> None:
    from duckclaw.ops import toolchain

    monkeypatch.setattr(toolchain.platform, "system", lambda: "Linux")
    root = tmp_path / "repo"
    bindir = root / ".venv" / "bin"
    bindir.mkdir(parents=True)
    py = bindir / "python3"
    py.write_text("#!/bin/sh\necho ok\n")
    py.chmod(py.stat().st_mode | stat.S_IXUSR)
    got = resolve_repo_pm2_python(root)
    assert got == str(py.resolve())


def test_resolve_repo_pm2_python_falls_back_to_sys_executable(tmp_path: Path) -> None:
    root = tmp_path / "norepo"
    root.mkdir()
    got = resolve_repo_pm2_python(root)
    assert got == str(Path(sys.executable).resolve())


def test_resolve_repo_pm2_python_prefers_windows_scripts(monkeypatch, tmp_path: Path) -> None:
    from duckclaw.ops import toolchain

    monkeypatch.setattr(toolchain.platform, "system", lambda: "Windows")
    root = tmp_path / "repo"
    scripts = root / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    py = scripts / "python.exe"
    py.write_bytes(b"")
    pyw = scripts / "pythonw.exe"
    pyw.write_bytes(b"")

    got = resolve_repo_pm2_python(root)
    assert got == str(pyw.resolve())


def test_render_db_writer_ecosystem_includes_windows_python_path() -> None:
    from duckclaw.ops.ecosystem_pm2 import render_ecosystem_runtime_cjs
    from duckclaw.ops.manager import render_db_writer_ecosystem_cjs

    content = render_db_writer_ecosystem_cjs()
    assert 'require("./ecosystem.runtime.cjs")' in content
    assert "resolveRepoPython" in content
    assert "windowsHide: true" in content
    assert "pythonw.exe" in render_ecosystem_runtime_cjs()
