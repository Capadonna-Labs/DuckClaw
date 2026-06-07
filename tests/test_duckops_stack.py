from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from duckops.cli import app


runner = CliRunner()


def test_root_package_exposes_stack_launcher_scripts() -> None:
    scripts = json.loads(Path("package.json").read_text(encoding="utf-8"))["scripts"]

    assert scripts["stack:up"] == "uv run duckops stack up"
    assert scripts["stack:status"] == "uv run duckops stack status"
    assert scripts["dev:admin"] == "pnpm --dir apps/duckclaw-admin dev"
    assert scripts["dev:local"] == "pnpm stack:up && pnpm admin:dev"


def test_duckops_stack_status_reports_pm2_processes_as_json(monkeypatch) -> None:
    import duckops.commands.stack as stack

    payload = [
        {"name": "DuckClaw-Gateway", "pm2_env": {"status": "online"}},
        {"name": "DuckClaw-DB-Writer", "pm2_env": {"status": "stopped"}},
    ]

    def fake_run(argv, **_kwargs):
        assert argv == ["pm2", "jlist"]
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(stack.subprocess, "run", fake_run)
    monkeypatch.setattr(stack, "_gateway_health_ok", lambda *_args, **_kwargs: True)

    result = runner.invoke(app, ["stack", "status", "--json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["provider"] == "pm2"
    assert data["services"]["DuckClaw-Gateway"]["status"] == "online"
    assert data["services"]["DuckClaw-Gateway"]["health_ok"] is True
    assert data["services"]["DuckClaw-DB-Writer"]["status"] == "stopped"
    assert data["all_ok"] is False


def test_duckops_stack_up_starts_gateway_and_db_writer_then_saves(monkeypatch, tmp_path: Path) -> None:
    import duckops.commands.stack as stack

    root = tmp_path
    config = root / "config"
    config.mkdir()
    (config / "ecosystem.api.config.cjs").write_text("module.exports = { apps: [] };\n", encoding="utf-8")
    (config / "ecosystem.db-writer.config.cjs").write_text("module.exports = { apps: [] };\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        if argv == ["pm2", "jlist"]:
            return SimpleNamespace(returncode=0, stdout="[]", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(stack, "_repo_root", lambda: root)
    monkeypatch.setattr(stack.subprocess, "run", fake_run)
    monkeypatch.setattr(stack, "_wait_for_gateway_health", lambda *_args, **_kwargs: True)

    result = runner.invoke(app, ["stack", "up", "--provider", "pm2", "--no-wait"])

    assert result.exit_code == 0, result.output
    assert ["pm2", "start", str(config / "ecosystem.api.config.cjs"), "--only", "DuckClaw-Gateway", "--update-env"] in calls
    assert ["pm2", "start", str(config / "ecosystem.db-writer.config.cjs"), "--only", "DuckClaw-DB-Writer", "--update-env"] in calls
    assert ["pm2", "save"] in calls

