from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from duckops.cli import app
from duckops.stack_readiness import needs_wizard_init

runner = CliRunner()


def test_needs_wizard_init_true_without_env(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    assert needs_wizard_init(tmp_path) is True


def test_needs_wizard_init_false_when_configured(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "api_gateways_pm2.json").write_text(
        '{"apps":[{"name":"DuckClaw-Gateway"}]}',
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "DUCKCLAW_ADMIN_EMAIL=admin@test.local\n"
        "DUCKCLAW_ADMIN_PASSWORD=secret-pass-9\n"
        "DUCKCLAW_ADMIN_API_KEY=real-key-abc\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DUCKCLAW_DISABLE_DOTENV", "0")
    assert needs_wizard_init(tmp_path) is False


def test_up_skip_init_fails_without_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "duckops.prerequisites.ensure_development_prerequisites",
        lambda *_a, **_k: True,
    )
    (tmp_path / "pyproject.toml").touch()
    result = runner.invoke(app, ["up", "--skip-init", "-C", str(tmp_path)])
    assert result.exit_code == 1
    assert "skip-init" in result.output.lower() or "configuración" in result.output.lower()


def test_up_orchestrates_when_configured(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "api_gateways_pm2.json").write_text(
        '{"apps":[{"name":"DuckClaw-Gateway"}]}',
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        "DUCKCLAW_ADMIN_EMAIL=a@b.co\n"
        "DUCKCLAW_ADMIN_PASSWORD=longpass99\n"
        "DUCKCLAW_ADMIN_API_KEY=real-key-abc\n",
        encoding="utf-8",
    )
    calls: list[str] = []

    monkeypatch.setattr(
        "duckops.prerequisites.ensure_development_prerequisites",
        lambda *_a, **_k: calls.append("bootstrap") or True,
    )
    monkeypatch.setattr("duckops.commands.up._run_migrate", lambda *_a, **_k: calls.append("migrate") or True)
    monkeypatch.setattr("duckops.commands.up._run_serve_stack", lambda *_a, **_k: calls.append("serve") or True)
    monkeypatch.setattr("duckops.commands.up._run_smoke", lambda *_a, **_k: calls.append("smoke") or True)
    monkeypatch.setattr(
        "duckops.admin_dev_server.wait_admin_http",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "duckops.admin_dev_server.start_admin_dev_server",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "duckops.admin_dev_server.open_admin_browser",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "duckops.post_up.run_post_up_loop",
        lambda *_a, **_k: 0,
    )

    result = runner.invoke(app, ["up", "--no-prompt", "--no-browser", "-C", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert calls == ["bootstrap", "migrate", "serve", "smoke"]
