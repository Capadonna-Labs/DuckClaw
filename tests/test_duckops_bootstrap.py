from __future__ import annotations

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
