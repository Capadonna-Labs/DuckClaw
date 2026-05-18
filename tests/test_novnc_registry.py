"""list_active_novnc_sessions (admin VNC tab)."""

import time

import pytest

from duckclaw.graphs import novnc_registry as nr


def test_list_active_novnc_sessions_empty() -> None:
    assert nr.list_active_novnc_sessions() == []


def test_list_active_novnc_sessions_returns_vnc_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_PUBLIC_URL", "https://gw.example")
    sid = f"sess_{id(monkeypatch)}"
    try:
        nr.register_session_port(sid, 16001)
        rows = nr.list_active_novnc_sessions()
        assert len(rows) == 1
        assert rows[0]["session_id"] == sid
        assert rows[0]["novnc_active"] is True
        assert rows[0]["seconds_remaining"] > 0
        assert "/api/v1/sandbox/novnc/view/" in rows[0]["vnc_url"]
    finally:
        nr.revoke_session(sid)


def test_list_active_novnc_sessions_skips_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    sid = f"exp_{id(monkeypatch)}"
    try:
        nr.register_session_port(sid, 16002)
        with nr._lock:
            nr._sessions[sid]["expires_at"] = time.time() - 1
        assert nr.list_active_novnc_sessions() == []
    finally:
        nr.revoke_session(sid)
