"""Spawn risk policy and import sanitization."""

from __future__ import annotations

from duckclaw.spawn_risk_policy import (
    is_high_risk_tool,
    sanitize_manifest_for_import,
    scan_text_for_secrets,
)


def test_is_high_risk_tool() -> None:
    assert is_high_risk_tool("admin_sql")
    assert is_high_risk_tool("execute_privileged_mutation")
    assert is_high_risk_tool("propose_sensitive_action")
    assert not is_high_risk_tool("read_sql")


def test_sanitize_manifest_strips_privileged_tools() -> None:
    manifest = {
        "id": "w",
        "read_only": False,
        "tool_surface": {"expose_privileged_mutation_tools": ["admin_sql"]},
    }
    out = sanitize_manifest_for_import(manifest)
    assert out["read_only"] is True
    assert out["tool_surface"]["expose_privileged_mutation_tools"] == []


def test_scan_text_for_secrets() -> None:
    assert scan_text_for_secrets("api_key=sk-abcdefghijklmnopqrstuvwxyz123456", label="f")
    assert not scan_text_for_secrets("harmless config", label="f")
