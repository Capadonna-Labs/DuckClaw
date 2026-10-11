from __future__ import annotations

from unittest.mock import patch

import pytest


def test_connector_has_auth_adb_requires_device_and_mcp() -> None:
    from duckclaw.admin_mcp_connectors import _connector_has_auth

    connector = {
        "auth_kind": "adb",
        "preset_id": "android",
        "metadata": {"connection_type": "adb_device"},
    }

    with patch(
        "duckclaw.mcp_android_adb.android_device_status",
        return_value={"adb_connected": True, "mcp_reachable": True},
    ):
        assert _connector_has_auth(None, connector) is True

    with patch(
        "duckclaw.mcp_android_adb.android_device_status",
        return_value={"adb_connected": False, "mcp_reachable": True},
    ):
        assert _connector_has_auth(None, connector) is False

    with patch(
        "duckclaw.mcp_android_adb.android_device_status",
        return_value={"adb_connected": True, "mcp_reachable": False},
    ):
        assert _connector_has_auth(None, connector) is False


def test_android_device_status_parses_battery() -> None:
    from duckclaw.mcp_android_adb import parse_battery_output

    raw = "  level: 77\n  status: 2\n"
    assert parse_battery_output(raw) == {"level_pct": 77, "charging": True}


def test_resolve_connector_endpoint_url_uses_live_mcp_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.mcp_android_adb import resolve_connector_endpoint_url

    monkeypatch.setenv("ANDROID_MCP_PORT", "9090")
    connector = {"auth_kind": "adb", "endpoint_url": "http://127.0.0.1:${ANDROID_MCP_PORT:-8080}/mcp"}
    assert resolve_connector_endpoint_url(connector) == "http://127.0.0.1:9090/mcp"


def test_android_adb_connect_uses_debug_port_override(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.mcp_android_adb import android_adb_connect

    monkeypatch.setenv("ANDROID_ADB_HOST", "192.0.2.1")
    monkeypatch.setenv("ANDROID_ADB_DEBUG_PORT", "5555")
    with patch(
        "duckclaw.mcp_android_adb._run_adb",
        return_value=(0, "connected to 192.0.2.1:39069", ""),
    ) as run:
        out = android_adb_connect(debug_port="39069")
    assert out["ok"] is True
    assert out["host"] == "192.0.2.1:39069"
    assert out["debug_port"] == "39069"
    run.assert_called_once_with(["connect", "192.0.2.1:39069"])


def test_android_adb_connect_pairs_before_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.mcp_android_adb import android_adb_connect

    monkeypatch.setenv("ANDROID_ADB_HOST", "192.0.2.1")
    calls: list[list[str]] = []

    def fake_run(args: list[str], *, timeout: float = 15.0):
        calls.append(args)
        if args[0] == "pair":
            return 0, "Successfully paired to 192.0.2.1:38417", ""
        return 0, "connected to 192.0.2.1:42961", ""

    with patch("duckclaw.mcp_android_adb._run_adb", side_effect=fake_run):
        out = android_adb_connect(
            debug_port="42961",
            pair_port="38417",
            pair_code="123456",
        )
    assert out["ok"] is True
    assert out["paired"] is True
    assert calls[0] == ["pair", "192.0.2.1:38417", "123456"]
    assert calls[1] == ["connect", "192.0.2.1:42961"]


def test_android_adb_connect_requires_host(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.mcp_android_adb import android_adb_connect

    monkeypatch.delenv("ANDROID_ADB_HOST", raising=False)
    out = android_adb_connect()
    assert out["ok"] is False
    assert "ANDROID_ADB_HOST" in out["error"]


def test_android_expand_notifications_no_device() -> None:
    from duckclaw.mcp_android_adb import android_expand_notifications

    with patch("duckclaw.mcp_android_adb.primary_adb_serial", return_value=""):
        out = android_expand_notifications()
    assert out["ok"] is False
    assert "no ADB device" in out["error"]


def test_android_expand_notifications_runs_adb() -> None:
    from duckclaw.mcp_android_adb import android_expand_notifications

    with patch("duckclaw.mcp_android_adb.primary_adb_serial", return_value="192.0.2.10:5555"):
        with patch(
            "duckclaw.mcp_android_adb._run_adb",
            return_value=(0, "", ""),
        ) as run:
            out = android_expand_notifications()
    assert out["ok"] is True
    assert out["serial"] == "192.0.2.10:5555"
    assert out["action"] == "expand-notifications"
    run.assert_called_once()
    assert run.call_args[0][0] == [
        "-s",
        "192.0.2.10:5555",
        "shell",
        "cmd",
        "statusbar",
        "expand-notifications",
    ]


def test_android_collapse_statusbar_runs_adb() -> None:
    from duckclaw.mcp_android_adb import android_collapse_statusbar

    with patch("duckclaw.mcp_android_adb.primary_adb_serial", return_value="serial1"):
        with patch(
            "duckclaw.mcp_android_adb._run_adb",
            return_value=(0, "", ""),
        ) as run:
            out = android_collapse_statusbar()
    assert out["ok"] is True
    assert out["action"] == "collapse"
    run.assert_called_once()
    assert "collapse" in run.call_args[0][0]


def test_android_review_and_dismiss_notifications_batches_visible_rows() -> None:
    from duckclaw.mcp_android_adb import android_review_and_dismiss_notifications

    raw_with_notification = (
        '<hierarchy bounds="[0,0][1080,2400]">'
        '<node text="Bloomberg" bounds="[44,300][240,340]" />'
        '<node text="OpenAI risk alert" bounds="[44,350][980,390]" />'
        "</hierarchy>"
    )
    raw_empty = '<hierarchy bounds="[0,0][1080,2400]"></hierarchy>'
    calls: list[list[str]] = []

    def fake_run(args: list[str], *, timeout: float = 15.0):
        calls.append(args)
        if "expand-notifications" in args:
            return 0, "", ""
        if "uiautomator" in args:
            return 0, "UI hierchary dumped", ""
        if "cat" in args:
            cat_calls = sum(1 for call in calls if "cat" in call)
            return 0, raw_with_notification if cat_calls == 1 else raw_empty, ""
        if "input" in args and "swipe" in args:
            return 0, "", ""
        if "collapse" in args:
            return 0, "", ""
        return 0, "", ""

    with patch("duckclaw.mcp_android_adb.primary_adb_serial", return_value="serial1"):
        with patch("duckclaw.mcp_android_adb._run_adb", side_effect=fake_run):
            out = android_review_and_dismiss_notifications(max_dismiss=3)

    assert out["ok"] is True
    assert out["processed_count"] == 1
    assert out["processed"][0]["title"] == "Bloomberg"
    assert any(call[:5] == ["-s", "serial1", "shell", "input", "swipe"] for call in calls)
