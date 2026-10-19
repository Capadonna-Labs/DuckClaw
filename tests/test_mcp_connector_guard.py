"""MCP connectors: per-tenant secrets and human confirmation (Alpaca presets as the example)."""

from __future__ import annotations

from typing import Any

import pytest

import duckclaw.forge.skills.mcp_connector_guard as guard
from duckclaw.mcp_connector_presets import clear_mcp_connector_presets_cache, preset_payload


class _FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def delete(self, key: str) -> None:
        self.data.pop(key, None)


@pytest.fixture()
def alpaca() -> dict[str, Any]:
    clear_mcp_connector_presets_cache()
    preset = preset_payload("alpaca")
    assert preset is not None
    return {**preset, "connector_id": "mcp_alpaca", "tenant_id": "t1", "metadata": {}}


@pytest.fixture()
def fake_redis(monkeypatch: Any) -> _FakeRedis:
    r = _FakeRedis()
    monkeypatch.setattr(guard, "_redis", lambda: r)
    return r


def test_presets_are_paper_by_default_and_live_is_separate(alpaca: dict[str, Any]) -> None:
    assert alpaca["launch_env"]["ALPACA_PAPER_TRADE"] == "true"
    live = preset_payload("alpaca_live")
    assert live["launch_env"]["ALPACA_PAPER_TRADE"] == "false"
    assert live["metadata"]["integration_env"]["ALPACA_API_KEY"] == "alpaca_live"


def test_stdio_env_uses_the_tenant_keys_never_the_hosts(alpaca: dict[str, Any], monkeypatch: Any) -> None:
    keys = {"alpaca": "tenant-key", "alpaca_secret": "tenant-secret"}
    monkeypatch.setattr(
        "duckclaw.integration_secrets.resolve_integration_api_key",
        lambda integration_id, **kw: keys.get(integration_id, "") if kw.get("tenant_id") == "t1" else "",
    )
    env = guard.apply_integration_env(object(), alpaca, {"ALPACA_API_KEY": "HOST", "PATH": "/bin"})
    assert env["ALPACA_API_KEY"] == "tenant-key" and env["ALPACA_SECRET_KEY"] == "tenant-secret"
    assert env["PATH"] == "/bin"

    keys.clear()  # a new user without keys must not inherit the host's account
    with pytest.raises(ValueError, match="faltan claves"):
        guard.apply_integration_env(object(), alpaca, {"ALPACA_API_KEY": "HOST"})


def test_order_tools_need_confirmation_and_reads_do_not(alpaca: dict[str, Any]) -> None:
    for name in ("place_stock_order", "cancel_all_orders", "close_all_positions", "replace_order_by_id"):
        assert guard.needs_confirmation(alpaca, name), name
    for name in ("get_account_info", "get_stock_snapshot", "get_news", "get_orders"):
        assert not guard.needs_confirmation(alpaca, name), name


def test_confirmed_tool_is_stored_not_run_and_approve_is_scoped(
    alpaca: dict[str, Any], fake_redis: _FakeRedis, monkeypatch: Any
) -> None:
    import duckclaw.forge.skills.mcp_connector_bridge as bridge

    calls: list[str] = []

    async def _never(db, connector, tool, args):  # noqa: ANN001
        calls.append(tool)
        return "ran"

    monkeypatch.setattr(bridge, "_call_connector_tool", _never)
    monkeypatch.setattr(
        "duckclaw.forge.skills.knowledge_tool_context.get_session_chat_id", lambda: "chat-1"
    )
    spec = type("Spec", (), {"name": "place_stock_order", "description": "order", "inputSchema": {
        "type": "object", "properties": {"symbol": {"type": "string"}, "qty": {"type": "number"}}}})()
    tool = bridge._wrap_connector_tool(object(), alpaca, spec)
    out = tool.invoke({"symbol": "AAPL", "qty": 1})
    assert "CONFIRMACIÓN PENDIENTE" in out and calls == []

    assert guard.take_pending(chat_id="chat-2", tenant_id="t1") is None  # another chat
    assert guard.take_pending(chat_id="chat-1", tenant_id="other") is None  # another tenant
    action = guard.take_pending(chat_id="chat-1", tenant_id="t1")
    assert action["tool"] == "place_stock_order" and action["args"] == {"symbol": "AAPL", "qty": 1}
    assert guard.take_pending(chat_id="chat-1", tenant_id="t1") is None  # consumed


def test_approve_runs_the_pending_action_and_reject_does_not(
    alpaca: dict[str, Any], fake_redis: _FakeRedis, monkeypatch: Any
) -> None:
    import duckclaw.forge.skills.mcp_connector_bridge as bridge
    from duckclaw.commands.fly_misc import execute_approve_reject

    ran: list[dict[str, Any]] = []

    async def _run(action):  # noqa: ANN001
        ran.append(action)
        return '{"status": "accepted"}'

    monkeypatch.setattr(bridge, "run_pending_action", _run)
    msg = guard.store_pending(alpaca, "place_stock_order", {"symbol": "SPY"}, chat_id="c1")
    action_id = msg.split("#", 1)[1].split("]", 1)[0]

    assert "Cancelada" in execute_approve_reject(None, "c1", False, action_id, tenant_id="t1")
    assert ran == []
    guard.store_pending(alpaca, "place_stock_order", {"symbol": "SPY"}, chat_id="c1")
    out = execute_approve_reject(None, "c1", True, "", tenant_id="t1")
    assert "ejecutada" in out and ran[0]["args"] == {"symbol": "SPY"}
    assert "No hay operación pendiente" in execute_approve_reject(None, "c1", True, "", tenant_id="t1")


def test_approve_and_reject_are_human_only() -> None:
    from duckclaw.commands.fly_dispatch import is_human_only_fly_command

    assert is_human_only_fly_command("approve") and is_human_only_fly_command("reject")


def test_broker_integrations_are_tenant_scoped_without_env_fallback() -> None:
    from duckclaw.integration_secrets import get_integration_secret_spec

    for integration_id in ("alpaca", "alpaca_secret", "alpaca_live", "alpaca_live_secret"):
        spec = get_integration_secret_spec(integration_id)
        assert spec is not None and spec.env_keys == () and spec.default_scope == "tenant"


def test_interactive_brokers_optional_login_and_confirmation(monkeypatch: Any) -> None:
    """Browser login by default (no stored credentials, never the host's); headless only when
    the user stored both; orders need confirmation."""
    clear_mcp_connector_presets_cache()
    ib = {**preset_payload("interactive_brokers"), "connector_id": "mcp_interactive_brokers", "tenant_id": "t1", "metadata": {}}
    assert ib["launch_env"]["IB_PAPER_TRADING"] == "true"
    stored: dict[str, str] = {}
    monkeypatch.setattr(
        "duckclaw.integration_secrets.resolve_integration_api_key",
        lambda integration_id, **kw: stored.get(integration_id, ""),
    )
    env = guard.apply_integration_env(object(), ib, {"IB_USERNAME": "HOST", "IB_PASSWORD_AUTH": "HOST", "HOME": "/h"})
    assert "IB_USERNAME" not in env and "IB_PASSWORD_AUTH" not in env and "IB_HEADLESS_MODE" not in env
    assert env["HOME"] == "/h"

    stored.update({"interactive_brokers_user": "me", "interactive_brokers_password": "pw"})
    env = guard.apply_integration_env(object(), ib, {})
    assert env["IB_USERNAME"] == "me" and env["IB_HEADLESS_MODE"] == "true"

    assert guard.needs_confirmation(ib, "place_order") and not guard.needs_confirmation(ib, "get_positions")
