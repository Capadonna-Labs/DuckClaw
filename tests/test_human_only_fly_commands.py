"""Approval commands must never run from a system turn (cron / heartbeat / loop)."""

from __future__ import annotations

from pathlib import Path

from duckclaw.commands.fly_dispatch import is_human_only_fly_command, parse_command


def test_approval_commands_are_human_only() -> None:
    for text in ("/approve-code 123", "/APPROVE_CODE 1", "/loop-approve x", "/approve-model a", "/reject-code 1"):
        name, _ = parse_command(text)
        assert is_human_only_fly_command(name), text
    for text in ("/help", "/session_report --status", "/goals"):
        assert not is_human_only_fly_command(parse_command(text)[0]), text


def test_gateway_checks_system_turns_before_running_fly_commands() -> None:
    src = (Path(__file__).resolve().parents[1] / "services" / "api-gateway" / "core" / "chat_graph_runner.py").read_text(
        encoding="utf-8"
    )
    guard = src.index("prepared.is_system_prompt and is_human_only_fly_command(cmd_name)")
    assert guard < src.index("fly_response = await invoke_legacy_fly_command(")
