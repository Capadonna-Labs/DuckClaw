"""noVNC: sanitización de sesión, token/TTL y proxy FastAPI."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from env_ids import TELEGRAM_TEST_USER_ID

from duckclaw.graphs.novnc_registry import (
    build_vnc_url,
    get_existing_token_and_port,
    register_session_port,
    resolve_token,
    sanitize_chat_to_session_id,
)


def test_sanitize_chat_to_session_id() -> None:
    assert sanitize_chat_to_session_id(TELEGRAM_TEST_USER_ID) == TELEGRAM_TEST_USER_ID
    assert "@" not in sanitize_chat_to_session_id("user@host")
    assert len(sanitize_chat_to_session_id("x" * 100)) <= 48


def test_register_resolve_and_expire() -> None:
    from duckclaw.graphs import novnc_registry as nr

    sid = "test_sess_novnc_registry_1"
    try:
        tok = register_session_port(sid, 16080)
        assert tok
        assert resolve_token(tok) == (sid, 16080)
        assert get_existing_token_and_port(sid)[0] == tok

        nr._sessions[sid]["expires_at"] = 0.0  # noqa: SLF001
        assert resolve_token(tok) == (None, None)
    finally:
        nr.revoke_session(sid)


def test_build_vnc_url_public(monkeypatch) -> None:
    from urllib.parse import parse_qs, urlparse

    monkeypatch.setenv("DUCKCLAW_PUBLIC_URL", "https://gw.example")
    # reload-ish: build_vnc_url reads env at call time
    u = build_vnc_url("mytok", 9999)
    assert "gw.example" in u
    assert "mytok" in u
    assert "/api/v1/sandbox/novnc/view/" in u
    q = parse_qs(urlparse(u).query)
    assert q.get("path", [""])[0] == "api/v1/sandbox/novnc/view/mytok/websockify"


def test_build_vnc_url_localhost(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_PUBLIC_URL", raising=False)
    u = build_vnc_url("ignored", 16080)
    assert "127.0.0.1:16080" in u


def test_novnc_proxy_404_invalid_token() -> None:
    from duckclaw.graphs.novnc_routes import build_novnc_router

    app = FastAPI()
    app.include_router(build_novnc_router(), prefix="/api/v1/sandbox/novnc")
    client = TestClient(app)
    r = client.get("/api/v1/sandbox/novnc/view/invalidtoken/vnc.html")
    assert r.status_code == 404
