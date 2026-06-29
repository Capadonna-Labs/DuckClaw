from __future__ import annotations

from pathlib import Path

import pytest


def test_ensure_ecosystem_runtime_writes_canonical_file(tmp_path: Path) -> None:
    from duckclaw.ops.ecosystem_pm2 import ensure_ecosystem_runtime, render_ecosystem_runtime_cjs

    root = tmp_path / "repo"
    root.mkdir()
    path = ensure_ecosystem_runtime(root)
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == render_ecosystem_runtime_cjs()
    assert "resolveRepoPython" in path.read_text(encoding="utf-8")


def test_refresh_session_path_prepends_uv_bin(monkeypatch, tmp_path: Path) -> None:
    from duckclaw.ops import toolchain

    uv_dir = tmp_path / "uvbin"
    uv_dir.mkdir()
    (uv_dir / "uv").write_text("", encoding="utf-8")

    monkeypatch.setattr(toolchain, "_uv_bin_dirs", lambda: [uv_dir])
    monkeypatch.setattr(toolchain.platform, "system", lambda: "Linux")
    monkeypatch.setenv("PATH", "")

    toolchain.refresh_session_path()
    assert str(uv_dir) in toolchain.os.environ["PATH"].split(toolchain.os.pathsep)


def test_run_pm2_checked_raises_on_nonzero(monkeypatch) -> None:
    from duckclaw.ops.toolchain import ToolchainError, run_pm2_checked

    def fake_run_pm2(*_args, **_kwargs):
        from types import SimpleNamespace

        return SimpleNamespace(returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr("duckclaw.ops.toolchain.run_pm2", fake_run_pm2)
    with pytest.raises(ToolchainError, match="boom"):
        run_pm2_checked("jlist")
