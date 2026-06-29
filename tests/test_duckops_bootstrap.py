from __future__ import annotations

import os
from pathlib import Path

from typer.testing import CliRunner

from duckops.cli import app
from duckops.prerequisites import ToolCheck, ensure_development_prerequisites

runner = CliRunner()


def test_bootstrap_check_only_lists_tools(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "duckops.prerequisites.check_all",
        lambda **_k: [
            ToolCheck("uv", True, "0.5", "/usr/bin/uv"),
            ToolCheck("Redis", False, "", "no ping"),
            ToolCheck("Node.js", True, "v20", "/usr/bin/node"),
            ToolCheck("npm", True, "10", "/usr/bin/npm"),
            ToolCheck("PM2", False, "", "missing"),
        ],
    )
    result = runner.invoke(app, ["bootstrap", "--check", "-C", str(tmp_path)])
    assert result.exit_code == 1
    assert "Redis" in result.output
    assert "PM2" in result.output


def test_bootstrap_yes_delegates_install(monkeypatch, tmp_path: Path) -> None:
    calls: list[bool] = []

    def _fake_ensure(*_a, **kw):
        calls.append(kw.get("assume_yes", False))
        return True

    monkeypatch.setattr("duckops.commands.bootstrap.ensure_development_prerequisites", _fake_ensure)
    result = runner.invoke(app, ["bootstrap", "--yes", "-C", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert calls == [True]


def test_ensure_skips_brew_without_yes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("duckops.prerequisites.platform.system", lambda: "Darwin")
    monkeypatch.setattr(
        "duckops.prerequisites.check_uv",
        lambda: ToolCheck("uv", True, "0.5", "uv"),
    )
    monkeypatch.setattr(
        "duckops.prerequisites.check_all",
        lambda **_k: [
            ToolCheck("uv", True, "0.5", "uv"),
            ToolCheck("Redis", False, "", "down"),
            ToolCheck("Node.js", True, "v20", "node"),
            ToolCheck("npm", True, "10", "npm"),
            ToolCheck("PM2", True, "5", "pm2"),
        ],
    )
    installed: list[str] = []

    monkeypatch.setattr(
        "duckops.prerequisites.install_redis",
        lambda *a, **k: installed.append("redis") or True,
    )

    out: list[str] = []
    ok = ensure_development_prerequisites(
        tmp_path,
        install=True,
        assume_yes=False,
        sync_python=False,
        print_fn=out.append,
    )
    assert ok is False
    assert installed == []
    assert any("Faltan" in line for line in out)


def test_init_no_bootstrap_flag_skips_prereq(monkeypatch, tmp_path: Path) -> None:
    called: list[bool] = []

    def _fake_ensure(*_a, **_k):
        called.append(True)
        return True

    monkeypatch.setattr("duckops.prerequisites.ensure_development_prerequisites", _fake_ensure)
    monkeypatch.setattr(
        "duckops.sovereign.runner.run_sovereign_wizard",
        lambda *_a, **_k: 0,
    )
    result = runner.invoke(app, ["init", "--no-bootstrap", "-C", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert called == []


def test_ensure_windows_check_only_does_not_block(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("duckops.prerequisites.platform.system", lambda: "Windows")
    monkeypatch.setattr(
        "duckops.prerequisites.check_all",
        lambda **_k: [
            ToolCheck("uv", True, "0.5", "uv"),
            ToolCheck("Redis", True, "pong", "redis://127.0.0.1:6379/0"),
            ToolCheck("Node.js", True, "v20", "node"),
            ToolCheck("npm", True, "10", "npm"),
            ToolCheck("pnpm", True, "9", "pnpm"),
            ToolCheck("PM2", True, "5", "pm2"),
        ],
    )
    out: list[str] = []
    ok = ensure_development_prerequisites(
        tmp_path,
        install=False,
        assume_yes=False,
        sync_python=False,
        print_fn=out.append,
    )
    assert ok is True
    assert any("[OK] uv" in line for line in out)


def test_ensure_windows_install_with_yes_runs_uv_sync(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("duckops.prerequisites.platform.system", lambda: "Windows")
    monkeypatch.setattr(
        "duckops.prerequisites.check_uv",
        lambda: ToolCheck("uv", True, "0.5", "uv"),
    )
    ok_tool = lambda name, ver="1", detail="ok": ToolCheck(name, True, ver, detail)
    monkeypatch.setattr("duckops.prerequisites.check_redis", lambda *a, **k: ok_tool("Redis", "pong"))
    monkeypatch.setattr("duckops.prerequisites.check_node", lambda: ok_tool("Node.js", "v20"))
    monkeypatch.setattr("duckops.prerequisites.check_npm", lambda: ok_tool("npm", "10"))
    monkeypatch.setattr("duckops.prerequisites.check_pnpm", lambda: ok_tool("pnpm", "9"))
    monkeypatch.setattr("duckops.prerequisites.check_pm2", lambda: ok_tool("PM2", "5"))
    monkeypatch.setattr(
        "duckops.prerequisites.check_all",
        lambda **_k: [
            ok_tool("uv", "0.5"),
            ok_tool("Redis", "pong"),
            ok_tool("Node.js", "v20"),
            ok_tool("npm", "10"),
            ok_tool("pnpm", "9"),
            ok_tool("PM2", "5"),
        ],
    )
    synced: list[Path] = []

    def _fake_sync(repo_root: Path, print_fn) -> bool:
        synced.append(repo_root)
        return True

    monkeypatch.setattr("duckops.prerequisites.run_uv_sync", _fake_sync)
    out: list[str] = []
    ok = ensure_development_prerequisites(
        tmp_path,
        install=True,
        assume_yes=True,
        sync_python=True,
        print_fn=out.append,
    )
    assert ok is True
    assert synced == [tmp_path]


def test_install_uv_windows_uses_powershell(monkeypatch) -> None:
    from duckops.prerequisites import install_uv

    monkeypatch.setattr("duckops.prerequisites.platform.system", lambda: "Windows")
    monkeypatch.setattr("duckops.prerequisites._winget_path", lambda: None)
    monkeypatch.setattr("duckops.prerequisites.shutil.which", lambda _name: None)
    calls: list[list[str]] = []

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        return 0

    monkeypatch.setattr("duckops.prerequisites._run_interactive", _fake_run)
    monkeypatch.setattr("duckops.prerequisites._augment_path_for_uv", lambda: None)
    assert install_uv(lambda _m: None) is False
    assert calls and calls[0][0] == "powershell"


def test_install_uv_windows_prefers_winget(monkeypatch) -> None:
    from duckops.prerequisites import install_uv

    winget_calls: list[str] = []
    which_calls = {"n": 0}

    def _fake_winget(package_id, print_fn):
        winget_calls.append(package_id)
        return True

    def _which(name: str):
        if name != "uv":
            return None
        which_calls["n"] += 1
        return "uv" if which_calls["n"] > 1 else None

    monkeypatch.setattr("duckops.prerequisites.platform.system", lambda: "Windows")
    monkeypatch.setattr("duckops.prerequisites._winget_path", lambda: "winget")
    monkeypatch.setattr("duckops.prerequisites._winget_install", _fake_winget)
    monkeypatch.setattr("duckops.prerequisites.shutil.which", _which)
    monkeypatch.setattr("duckops.prerequisites._augment_path_for_uv", lambda: None)

    assert install_uv(lambda _m: None) is True
    assert winget_calls == ["astral-sh.uv"]


def test_ensure_uv_available_skips_install_when_present(monkeypatch) -> None:
    from duckops.prerequisites import ensure_uv_available

    monkeypatch.setattr("duckops.prerequisites.shutil.which", lambda name: "uv" if name == "uv" else None)
    called: list[bool] = []
    monkeypatch.setattr(
        "duckops.prerequisites.install_uv",
        lambda print_fn: called.append(True) or True,
    )
    assert ensure_uv_available() is True
    assert called == []


def test_explain_prerequisite_failures_lists_missing_tools(monkeypatch) -> None:
    from duckops.prerequisites import explain_prerequisite_failures

    monkeypatch.setattr(
        "duckops.prerequisites.check_all",
        lambda **_k: [
            ToolCheck("Redis", False, "", "no ping"),
            ToolCheck("PM2", False, "", "missing"),
        ],
    )
    lines: list[str] = []
    explain_prerequisite_failures(lines.append, failed_step="Redis")
    text = "\n".join(lines)
    assert "FALLO EN PREREQUISITOS" in text
    assert "Paso que fallo: Redis" in text
    assert "[FALTA] Redis" in text
    assert "[FALTA] PM2" in text
    assert "Solucion:" in text


def test_find_redis_server_windows_uses_program_files(monkeypatch, tmp_path: Path) -> None:
    from duckops.prerequisites import _find_redis_server_windows

    redis_dir = tmp_path / "Redis"
    redis_dir.mkdir()
    (redis_dir / "redis-server.exe").write_text("", encoding="utf-8")
    monkeypatch.setattr("duckops.prerequisites._is_windows", lambda: True)
    monkeypatch.setattr("duckops.prerequisites._windows_redis_dirs", lambda: [redis_dir])
    monkeypatch.setattr("duckops.prerequisites.shutil.which", lambda _name: None)
    found = _find_redis_server_windows()
    assert found == str(redis_dir / "redis-server.exe")


def test_augment_path_for_windows_includes_npm_global(monkeypatch, tmp_path: Path) -> None:
    from duckops.prerequisites import augment_path_for_windows_tools

    npm_global = tmp_path / "npm-global"
    npm_global.mkdir()
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr("duckops.prerequisites._is_windows", lambda: True)
    monkeypatch.setattr("duckops.prerequisites._refresh_windows_user_path", lambda: None)
    monkeypatch.setattr("duckops.prerequisites._windows_node_dirs", lambda: [])
    monkeypatch.setattr("duckops.prerequisites._windows_redis_dirs", lambda: [])
    monkeypatch.setattr("duckops.prerequisites._uv_bin_dirs", lambda: [])
    monkeypatch.setattr(
        "duckops.prerequisites._windows_npm_global_dirs",
        lambda: [npm_global],
    )
    monkeypatch.setenv("PATH", "")
    augment_path_for_windows_tools()
    assert str(npm_global) in os.environ["PATH"]


def test_run_interactive_missing_command_returns_127(monkeypatch) -> None:
    from duckops.prerequisites import _run_interactive

    monkeypatch.setattr("duckops.prerequisites.subprocess.run", _missing_subprocess_run)
    assert _run_interactive(["comando-inexistente-duckclaw-test"]) == 127


def _missing_subprocess_run(*_args, **_kwargs):
    raise FileNotFoundError(2, "El sistema no puede encontrar el archivo especificado")
