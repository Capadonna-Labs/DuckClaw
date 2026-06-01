from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from duckops.cli import app


runner = CliRunner()


def test_duckops_exposes_script_replacement_commands() -> None:
    commands = (
        ["ingress", "serve-admin", "--dry-run"],
        ["ingress", "restore-admin-serve", "--dry-run"],
        ["ingress", "telegram-check", "--dry-run"],
        ["ingress", "telegram-register-webhooks", "--dry-run"],
        ["ingress", "telegram-start", "--dry-run"],
        ["mcp", "prefetch", "reddit", "--dry-run"],
        ["comfyui", "start", "--dry-run"],
        ["db", "bootstrap", "--dry-run"],
        ["db", "check-locks", "--dry-run"],
        ["db", "authorized-users", "--dry-run"],
        ["deploy", "spawn-install", "--dry-run"],
    )
    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, (command, result.output)
        assert "dry-run" in result.output.lower()


def test_shell_wrappers_delegate_to_duckops() -> None:
    wrappers = {
        "scripts/tailscale_serve_admin.sh": "duckops ingress serve-admin",
        "scripts/prefetch_mcp_reddit.sh": "duckops mcp prefetch reddit",
        "scripts/start_comfyui.sh": "duckops comfyui start",
    }
    for path, expected in wrappers.items():
        text = Path(path).read_text(encoding="utf-8")
        assert expected in text


def test_one_off_scripts_removed_from_active_scripts() -> None:
    removed = (
        "scripts/crm_origin_check.py",
        "scripts/openweather_city.py",
        "scripts/experimental/remap_weights.py",
        "scripts/experimental/LOCAL_EXPERIMENTAL_SCRIPTS.md",
    )
    for path in removed:
        assert not Path(path).exists()
