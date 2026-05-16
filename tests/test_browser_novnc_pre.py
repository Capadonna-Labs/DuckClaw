"""ensure_browser_novnc_session y flag DUCKCLAW_BROWSER_NOVNC_PRE_DM (worker factory)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_ensure_browser_novnc_session_returns_none_without_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs import sandbox as sb

    monkeypatch.setattr(sb, "_docker_available", lambda: False)
    assert sb.ensure_browser_novnc_session("w1", "sess_a") is None


def test_ensure_browser_novnc_session_provisions_and_returns_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs import sandbox as sb

    monkeypatch.setenv("STRIX_BROWSER_PUBLISH_NOVNC", "1")
    monkeypatch.setenv("DUCKCLAW_PUBLIC_URL", "https://gw.example")

    class _FakeContainer:
        attrs = {"NetworkSettings": {"Ports": {"6080/tcp": [{"HostPort": "15555"}]}}}

        def reload(self) -> None:
            pass

    fake_c = _FakeContainer()

    mgr = MagicMock()
    mgr._session_dirs.return_value = (MagicMock(), MagicMock())
    mgr._get_or_create_container.return_value = fake_c

    def _do_refresh(sid: str, _container: object) -> None:
        from duckclaw.graphs import novnc_registry as nr

        nr.register_session_port(sid, 15555)

    mgr._refresh_browser_novnc.side_effect = _do_refresh

    monkeypatch.setattr(sb, "_docker_available", lambda: True)
    monkeypatch.setattr(sb, "_get_manager", lambda: mgr)
    monkeypatch.setattr(sb, "load_security_policy", lambda _w: MagicMock())
    monkeypatch.setattr(sb, "_load_allowed_secrets", lambda _p: {})
    monkeypatch.setattr(sb, "_browser_image_name", lambda: "duckclaw/browser-env:latest")

    try:
        url = sb.ensure_browser_novnc_session("PQRSD-Assistant", "chat_1")
        assert url
        assert "/api/v1/sandbox/novnc/view/" in url
        assert "vnc.html" in url
        mgr._get_or_create_container.assert_called_once()
        mgr._refresh_browser_novnc.assert_called_once_with("chat_1", fake_c)
    finally:
        from duckclaw.graphs import novnc_registry as nr

        nr.revoke_session("chat_1")


def test_novnc_pre_dm_always_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.workers import factory as fac

    monkeypatch.delenv("DUCKCLAW_BROWSER_NOVNC_PRE_DM", raising=False)
    assert fac._novnc_pre_dm_always_enabled() is False

    monkeypatch.setenv("DUCKCLAW_BROWSER_NOVNC_PRE_DM", "always")
    assert fac._novnc_pre_dm_always_enabled() is True


def test_schedule_run_browser_novnc_uses_heartbeat_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs import novnc_registry as nr
    from duckclaw.workers import factory as fac

    calls: list[tuple[str, str]] = []

    def fake_is_on(_tid: str, _cid: str) -> bool:
        return True

    def fake_schedule(_tid: str, _cid: str, _uid: str, text: str, **_kw: object) -> None:
        calls.append(("schedule", text))

    monkeypatch.setenv("DUCKCLAW_BROWSER_NOVNC_PRE_DM", "0")
    monkeypatch.setattr(
        "duckclaw.graphs.chat_heartbeat.is_chat_heartbeat_enabled",
        fake_is_on,
    )
    monkeypatch.setattr(
        "duckclaw.graphs.chat_heartbeat.schedule_chat_heartbeat_dm",
        fake_schedule,
    )

    from env_ids import TELEGRAM_TEST_USER_ID

    state = {
        "tenant_id": "PQRS",
        "chat_id": TELEGRAM_TEST_USER_ID,
        "user_id": TELEGRAM_TEST_USER_ID,
        "subagent_instance_label": "PQRSD-Assistant 1",
        "heartbeat_plan_title": "Plan",
    }
    sid = TELEGRAM_TEST_USER_ID
    nr.register_session_port(sid, 15555)
    try:
        vnc = (
            "https://gw.example/api/v1/sandbox/novnc/view/tok/vnc.html"
            "?autoconnect=1&path=api%2Fv1%2Fsandbox%2Fnovnc%2Fview%2Ftok%2Fwebsockify"
        )
        fac._schedule_run_browser_novnc_tool_heartbeat(
            state,
            routing_worker_id="PQRSD-Assistant",
            vnc_url=vnc,
            novnc_session_id=sid,
        )
        fac._schedule_run_browser_novnc_tool_heartbeat(
            state,
            routing_worker_id="PQRSD-Assistant",
            vnc_url=vnc,
            novnc_session_id=sid,
        )
        assert len(calls) == 2
        assert "noVNC" in calls[0][1]
        assert "https://gw.example/api/v1/sandbox/novnc/view/" in calls[0][1]
        assert "gw.example" not in calls[1][1]
        assert "get_browser_session_url" in calls[1][1]
    finally:
        nr.revoke_session(sid)


def test_consume_initial_vnc_telegram_link_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs import novnc_registry as nr

    monkeypatch.setenv("DUCKCLAW_BROWSER_NOVNC_TTL_S", "600")
    sid = "sess_consume_test"
    nr.register_session_port(sid, 14000)
    try:
        assert nr.consume_initial_vnc_telegram_link(sid) is True
        assert nr.consume_initial_vnc_telegram_link(sid) is False
    finally:
        nr.revoke_session(sid)


def test_schedule_run_browser_novnc_fallback_when_heartbeat_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.workers import factory as fac

    sent: list[str] = []

    def fake_is_on(_tid: str, _cid: str) -> bool:
        return False

    def fake_send(**kwargs: object) -> None:
        sent.append(str(kwargs.get("plain_text") or ""))

    monkeypatch.setenv("DUCKCLAW_BROWSER_NOVNC_PRE_DM", "always")
    monkeypatch.setattr(
        "duckclaw.graphs.chat_heartbeat.is_chat_heartbeat_enabled",
        fake_is_on,
    )
    monkeypatch.setattr(
        "duckclaw.graphs.chat_heartbeat._resolve_heartbeat_outbound_bot_token",
        lambda _o, _r: "token",
    )
    monkeypatch.setattr(
        "duckclaw.integrations.telegram.telegram_outbound_sync.send_long_plain_text_markdown_v2_chunks_sync",
        lambda **kw: fake_send(**kw) or 1,
    )

    from env_ids import TELEGRAM_TEST_USER_ID

    state = {
        "chat_id": TELEGRAM_TEST_USER_ID,
        "outbound_telegram_bot_token": "",
    }
    fac._send_novnc_pre_dm_fallback(
        state,
        (
            "https://gw.example/api/v1/sandbox/novnc/view/tok/vnc.html"
            "?autoconnect=1&path=api%2Fv1%2Fsandbox%2Fnovnc%2Fview%2Ftok%2Fwebsockify"
        ),
        routing_worker_id="PQRSD-Assistant",
    )
    # Thread — wait briefly
    import time

    time.sleep(0.15)
    assert sent, "expected plain_text send"
    assert "https://gw.example/api/v1/sandbox/novnc/view/" in sent[0]
