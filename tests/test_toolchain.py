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


def test_resolve_pnpm_executable_prefers_cmd_on_windows(monkeypatch, tmp_path: Path) -> None:
    from duckclaw.ops.toolchain import resolve_pnpm_executable

    npm_dir = tmp_path / "npm"
    npm_dir.mkdir()
    cmd = npm_dir / "pnpm.cmd"
    cmd.write_text("@echo pnpm\n", encoding="utf-8")

    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("duckclaw.ops.toolchain.platform.system", lambda: "Windows")
    monkeypatch.setattr("duckclaw.ops.toolchain.shutil.which", lambda _name: None)

    assert resolve_pnpm_executable() == str(cmd)


def test_resolve_pnpm_finds_bin_even_when_not_on_path(monkeypatch, tmp_path: Path) -> None:
    from duckclaw.ops.toolchain import resolve_pnpm_executable

    npm_dir = tmp_path / "npm-global"
    npm_dir.mkdir()
    cmd = npm_dir / "pnpm.cmd"
    cmd.write_text("@echo pnpm\n", encoding="utf-8")

    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("duckclaw.ops.toolchain.platform.system", lambda: "Windows")
    monkeypatch.setattr(
        "duckclaw.ops.toolchain._npm_global_bin_dirs",
        lambda: [npm_dir],
    )
    monkeypatch.setattr("duckclaw.ops.toolchain.shutil.which", lambda _name: None)

    assert resolve_pnpm_executable() == str(cmd)


def test_prepend_path_dirs_skips_existing_entries(monkeypatch, tmp_path: Path) -> None:
    from duckclaw.ops import toolchain

    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    monkeypatch.setenv("PATH", str(first))
    toolchain._prepend_path_dirs([first, second])
    parts = toolchain.os.environ["PATH"].split(toolchain.os.pathsep)
    assert parts.count(str(first)) == 1
    assert str(second) in parts


def test_refresh_session_path_does_not_grow_path_on_repeat(monkeypatch, tmp_path: Path) -> None:
    from duckclaw.ops import toolchain

    npm_dir = tmp_path / "npm"
    npm_dir.mkdir()
    monkeypatch.setattr(toolchain.platform, "system", lambda: "Windows")
    monkeypatch.setenv("PATH", r"C:\seed\bin")
    monkeypatch.setattr(toolchain, "_refresh_windows_registry_path", lambda: None)
    monkeypatch.setattr(
        toolchain,
        "_npm_global_bin_dirs",
        lambda: [npm_dir],
    )
    monkeypatch.setattr(toolchain, "_path_candidate_dirs", lambda repo_root=None: [])

    toolchain.refresh_session_path()
    once = len(toolchain.os.environ["PATH"])
    toolchain.refresh_session_path()
    twice = len(toolchain.os.environ["PATH"])
    assert twice == once


def test_run_pm2_checked_raises_on_nonzero(monkeypatch) -> None:
    from duckclaw.ops.toolchain import ToolchainError, run_pm2_checked

    def fake_run_pm2(*_args, **_kwargs):
        from types import SimpleNamespace

        return SimpleNamespace(returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr("duckclaw.ops.toolchain.run_pm2", fake_run_pm2)
    with pytest.raises(ToolchainError, match="boom"):
        run_pm2_checked("jlist")
