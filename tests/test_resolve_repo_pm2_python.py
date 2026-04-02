"""resolve_repo_pm2_python: PM2 debe usar el venv del repo si existe."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from duckclaw.ops.manager import resolve_repo_pm2_python


def test_resolve_repo_pm2_python_prefers_dot_venv(tmp_path: Path) -> None:
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
