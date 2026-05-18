"""Puerto del gateway desde .env (fuente única)."""

from __future__ import annotations

from pathlib import Path

from duckclaw.gateway_port import resolve_gateway_port


def test_resolve_gateway_port_from_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "DUCKCLAW_GATEWAY_PORT=9001\nDUCKCLAW_PM2_PROCESS_NAME=DuckClaw-Gateway\n",
        encoding="utf-8",
    )
    assert resolve_gateway_port(tmp_path) == 9001


def test_resolve_gateway_port_proposed_overlay(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("DUCKCLAW_GATEWAY_PORT=9000\n", encoding="utf-8")
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "dotenv_wizard_proposed.env").write_text(
        "DUCKCLAW_GATEWAY_PORT=9002\n", encoding="utf-8"
    )
    assert resolve_gateway_port(tmp_path) == 9002
