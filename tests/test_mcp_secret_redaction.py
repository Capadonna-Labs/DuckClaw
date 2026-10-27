"""A connector's own credentials never come back to the model (results, raised errors) nor reach the audit row."""
from __future__ import annotations

import json

import pytest

from duckclaw.forge.skills import mcp_call_audit, mcp_connector_bridge as bridge
from duckclaw.forge.skills.mcp_secret_redaction import REDACTED, connector_secrets, redact_secrets

TOKEN = "tskey-api-AbCdEf1234567890"


def test_redacts_raw_and_json_escaped_forms_and_longest_first() -> None:
    escaped = json.dumps('pre"fix-secret-9999')[1:-1]
    text = f'Authorization: Bearer {TOKEN}; body={{"k": "{escaped}"}} and {TOKEN}-extended'
    out = redact_secrets(text, ['pre"fix-secret-9999', TOKEN, TOKEN + "-extended"][::-1])
    assert TOKEN not in out and "secret-9999" not in out and out.count(REDACTED) >= 3


def test_short_values_are_not_treated_as_secrets() -> None:
    connector = {"auth_kind": "none", "transport": "stdio", "launch_env": {"DEBUG": "1", "MODE": "prod", "KEY": TOKEN}}
    assert connector_secrets(None, connector) == [TOKEN]


def test_bearer_token_and_launch_env_are_collected(monkeypatch) -> None:
    from duckclaw import admin_mcp_connectors

    monkeypatch.setattr(admin_mcp_connectors, "resolve_connector_bearer_token", lambda db, c: TOKEN)
    got = connector_secrets(object(), {"auth_kind": "bearer", "transport": "streamable_http", "launch_env": {"X": "another-long-secret"}})
    assert set(got) == {TOKEN, "another-long-secret"}


def test_a_resolver_failure_returns_no_secrets_instead_of_raising(monkeypatch) -> None:
    from duckclaw import admin_mcp_connectors

    def boom(db, c):
        raise RuntimeError("vault locked")

    monkeypatch.setattr(admin_mcp_connectors, "resolve_connector_bearer_token", boom)
    assert connector_secrets(object(), {"auth_kind": "bearer", "transport": "streamable_http"}) == []


class _Spec:
    name = "list_devices"
    description = "x"
    inputSchema = {"type": "object", "properties": {}}


def _tool(monkeypatch, behaviour):
    from duckclaw import admin_mcp_connectors

    monkeypatch.setattr(admin_mcp_connectors, "resolve_connector_bearer_token", lambda db, c: TOKEN)
    rows: list = []
    monkeypatch.setattr(mcp_call_audit, "record_mcp_call", lambda *a, **k: rows.append(k))

    async def fake_call(db, connector, tool_name, arguments):
        return behaviour()

    monkeypatch.setattr(bridge, "_call_connector_tool", fake_call)
    connector = {"connector_id": "mcp_t", "auth_kind": "bearer", "transport": "streamable_http", "tool_allowlist": ["*"], "tool_denylist": [], "read_only": True}
    return bridge._wrap_connector_tool(object(), connector, _Spec()), rows


def test_a_result_that_echoes_the_key_is_scrubbed_before_the_model_and_the_audit(monkeypatch) -> None:
    tool, rows = _tool(monkeypatch, lambda: json.dumps({"error": f"401 for https://api.example/x?key={TOKEN}"}))
    out = tool.invoke({})
    assert TOKEN not in out and REDACTED in out
    assert rows[0]["status"] == "error" and TOKEN not in rows[0]["error"] and REDACTED in rows[0]["error"]


def test_an_exception_that_echoes_the_key_is_raised_scrubbed(monkeypatch) -> None:
    def boom():
        raise ValueError(f"connect failed, header Authorization: Bearer {TOKEN}")

    tool, rows = _tool(monkeypatch, boom)
    with pytest.raises(RuntimeError) as exc:
        tool.invoke({})
    assert TOKEN not in str(exc.value) and REDACTED in str(exc.value)
    assert rows[0]["error"] == "ValueError"                                        # the audit keeps only the class name


def test_a_clean_exception_is_raised_unchanged(monkeypatch) -> None:
    def boom():
        raise ValueError("timeout")

    tool, _rows = _tool(monkeypatch, boom)
    with pytest.raises(ValueError, match="timeout"):
        tool.invoke({})
