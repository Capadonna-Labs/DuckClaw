"""Tests for Tailscale Bridge skill."""

from __future__ import annotations

from unittest.mock import patch


def test_tailscale_status_parse_json_active() -> None:
    """Parse JSON output returns Active when peers exist."""
    from duckclaw.forge.skills.tailscale_bridge import _parse_status_output

    raw = '{"Self":{"Online":true},"Peer":{"1":{"HostName":"server","TailscaleIPs":["192.0.2.10"]}}}'
    status, peers = _parse_status_output(raw)
    assert status == "Active"
    assert "192.0.2.10" in str(peers)
    assert "server" in str(peers)


def test_tailscale_status_parse_json_down() -> None:
    """Parse JSON output returns Down when no peers and offline."""
    from duckclaw.forge.skills.tailscale_bridge import _parse_status_output

    raw = '{"Self":{"Online":false},"Peer":{}}'
    status, peers = _parse_status_output(raw)
    assert status == "Down"
    assert peers == []


def test_tailscale_status_parse_empty() -> None:
    """Empty output returns Down."""
    from duckclaw.forge.skills.tailscale_bridge import _parse_status_output

    status, peers = _parse_status_output("")
    assert status == "Down"
    assert peers == []


def test_tailscale_status_impl_with_mock() -> None:
    """_tailscale_status_impl returns Active when tailscale status --json succeeds."""
    import duckclaw.forge.skills.tailscale_bridge as m

    with patch.object(m, "_run_tailscale_status", return_value='{"Self":{"Online":true},"Peer":{"1":{"HostName":"server","TailscaleIPs":["192.0.2.10"]}}}'):
        result = m._tailscale_status_impl()
        assert "ConnectionStatus: Active" in result
        assert "192.0.2.10" in result or "server" in result


def test_register_tailscale_skill_no_config() -> None:
    """register_tailscale_skill does nothing when config is None."""
    from duckclaw.forge.skills.tailscale_bridge import register_tailscale_skill

    tools = []
    register_tailscale_skill(tools, None)
    assert len(tools) == 0


def test_register_tailscale_skill_disabled() -> None:
    """register_tailscale_skill does nothing when tailscale_enabled is False."""
    from duckclaw.forge.skills.tailscale_bridge import register_tailscale_skill

    tools = []
    register_tailscale_skill(tools, {"tailscale_enabled": False})
    assert len(tools) == 0


def test_register_tailscale_skill_adds_tool_when_available() -> None:
    """register_tailscale_skill adds tool when tailscale is in PATH and enabled."""
    from duckclaw.forge.skills.tailscale_bridge import register_tailscale_skill

    tools = []
    with patch("duckclaw.forge.skills.tailscale_bridge.shutil.which", return_value="/usr/bin/tailscale"):
        register_tailscale_skill(tools, {"tailscale_enabled": True})
    if tools:
        assert len(tools) == 1
        assert tools[0].name == "tailscale_status"


# --- tailscale_devices: official API, read-only, key from Integraciones ---------------------------------------------------------------------------------

from datetime import datetime, timezone

_NOW = datetime(2026, 10, 27, 17, 0, tzinfo=timezone.utc)
_DEVICES = [
    {"hostname": "duckclaw-prod-eu-1", "os": "linux", "addresses": ["100.79.185.46"], "connectedToControl": True, "lastSeen": "2026-10-27T16:59:00Z", "clientVersion": "1.104.2", "expires": "2027-04-01T00:00:00Z", "authorized": True},
    {"name": "capadonna-box-1.tailc85db0.ts.net", "os": "linux", "addresses": ["100.117.195.82"], "connectedToControl": False, "lastSeen": "2026-10-22T10:00:00Z", "updateAvailable": True, "expires": "2026-11-05T00:00:00Z"},
    {"hostname": "a70", "os": "android", "addresses": ["100.69.96.111"], "lastSeen": "2026-03-30T00:00:00Z", "keyExpiryDisabled": True, "tags": ["tag:phone"]},
]


def test_summary_flags_offline_updates_and_expiring_keys_without_exposing_keys() -> None:
    import duckclaw.forge.skills.tailscale_bridge as m

    out = m.summarize_devices(_DEVICES, now=_NOW)
    by = {r["dispositivo"]: r for r in out["dispositivos"]}
    assert (out["total"], out["en_linea"], out["mostrados"]) == (3, 1, 3)
    assert by["duckclaw-prod-eu-1"]["problemas"] == [] and by["duckclaw-prod-eu-1"]["en_linea"] is True
    assert by["capadonna-box-1"]["problemas"] == ["sin conexión", "actualización disponible", "clave vence en 8 d"]   # hostname falls back to the short name
    assert by["a70"]["en_linea"] is False and by["a70"]["problemas"] == ["sin conexión"]                              # no connectedToControl: stale lastSeen; expiry disabled = no warning
    assert "machineKey" not in str(out) and "nodeKey" not in str(out)


def test_summary_filters_by_name_and_by_problems() -> None:
    import duckclaw.forge.skills.tailscale_bridge as m

    assert [r["dispositivo"] for r in m.summarize_devices(_DEVICES, now=_NOW, only_problems=True)["dispositivos"]] == ["capadonna-box-1", "a70"]
    assert [r["dispositivo"] for r in m.summarize_devices(_DEVICES, now=_NOW, name_contains="PROD")["dispositivos"]] == ["duckclaw-prod-eu-1"]
    assert m.summarize_devices([], now=_NOW) == {"total": 0, "en_linea": 0, "mostrados": 0, "dispositivos": []}


def _keys(monkeypatch, api_key="tskey-api-SECRET1234567890", tailnet="me@example.com"):
    import duckclaw.forge.skills.tailscale_bridge as m
    import duckclaw.integration_secrets as s

    monkeypatch.setattr(m, "_hub_db", lambda: None)                                   # never open the real hub from a unit test
    monkeypatch.setattr(s, "resolve_integration_api_key", lambda i, db=None, tenant_id="default": {"tailscale_api_key": api_key, "tailscale_tailnet": tailnet}.get(i, ""))


def test_keys_are_found_in_the_hub_when_the_worker_vault_does_not_have_them(monkeypatch) -> None:
    import duckclaw.forge.skills.tailscale_bridge as m
    import duckclaw.integration_secrets as s

    vault, hub = object(), object()
    monkeypatch.setattr(m, "_hub_db", lambda: hub)
    monkeypatch.setattr(s, "resolve_integration_api_key", lambda i, db=None, tenant_id="default": ({"tailscale_api_key": "tskey-api-K1234567890", "tailscale_tailnet": "me@example.com"}.get(i, "") if db is hub else ""))
    assert m._integration_keys(vault, "t1") == ("tskey-api-K1234567890", "me@example.com")
    assert m._tailscale_devices_tool({"tailscale_enabled": True}, db=vault, tenant_id="t1") is not None       # offered although the vault has nothing
    monkeypatch.setattr(m, "_hub_db", lambda: None)
    assert m._integration_keys(vault, "t1") == ("", "")


def test_impl_uses_the_tenant_keys_and_never_returns_them(monkeypatch) -> None:
    import json

    import duckclaw.forge.skills.tailscale_bridge as m

    _keys(monkeypatch)
    seen = {}

    def fetch(key, tailnet):
        seen["args"] = (key, tailnet)
        return _DEVICES

    out = m._tailscale_devices_impl(object(), "t1", fetch=fetch)
    assert seen["args"] == ("tskey-api-SECRET1234567890", "me@example.com")
    assert json.loads(out)["total"] == 3 and "SECRET" not in out


def test_impl_reports_missing_keys_and_http_errors_without_leaking_the_key(monkeypatch) -> None:
    import urllib.error

    import duckclaw.forge.skills.tailscale_bridge as m

    _keys(monkeypatch, api_key="", tailnet="")
    assert "faltan la API key y el nombre de la tailnet" in m._tailscale_devices_impl(object(), "t1")
    _keys(monkeypatch)

    def http_401(key, tailnet):
        raise urllib.error.HTTPError(f"https://api.tailscale.com/x?key={key}", 401, "Unauthorized", {}, None)

    msg = m._tailscale_devices_impl(object(), "t1", fetch=http_401)
    assert "401" in msg and "inválida o venció" in msg and "SECRET" not in msg

    def boom(key, tailnet):
        raise RuntimeError(f"connection to {key} failed")

    msg = m._tailscale_devices_impl(object(), "t1", fetch=boom)
    assert "RuntimeError" in msg and "SECRET" not in msg


def test_api_tool_is_offered_only_when_both_keys_are_stored(monkeypatch) -> None:
    import duckclaw.forge.skills.tailscale_bridge as m

    _keys(monkeypatch, api_key="", tailnet="")
    assert m._tailscale_devices_tool({"tailscale_enabled": True}, db=object()) is None
    _keys(monkeypatch)
    assert m._tailscale_devices_tool({"tailscale_enabled": True}, db=None) is None            # no vault, no key lookup
    assert m._tailscale_devices_tool({"tailscale_enabled": False}, db=object()) is None
    tool = m._tailscale_devices_tool({"tailscale_enabled": True}, db=object(), tenant_id="t1")
    assert tool is not None and tool.name == "tailscale_devices"
    tools: list = []
    m.register_tailscale_skill(tools, {"tailscale_enabled": True}, db=object(), tenant_id="t1")
    assert "tailscale_devices" in {t.name for t in tools}


def test_the_api_host_is_fixed_and_the_tool_is_read_only() -> None:
    import inspect

    import duckclaw.forge.skills.tailscale_bridge as m

    assert m._API_BASE == "https://api.tailscale.com/api/v2"
    src = inspect.getsource(m)
    for verb in ('method="POST"', 'method="PUT"', 'method="DELETE"', 'method="PATCH"', "urlopen(url"):
        assert verb not in src
