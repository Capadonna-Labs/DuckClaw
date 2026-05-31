"""Admin auth sessions: login, /me TTL refresh, logout, rate limit."""
from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient


def _login(client: TestClient, email: str = "admin@test.local", password: str = "secret123"):
    return client.post("/api/v1/admin/auth/login", json={"email": email, "password": password})


def test_login_sets_cookies_and_user_payload(gateway_admin_client: TestClient) -> None:
    r = _login(gateway_admin_client)
    assert r.status_code == 200
    data = r.json()
    assert "user" in data
    assert data["user"]["email"] == "admin@test.local"
    assert data["user"]["rol"] == "admin"
    assert "session" in r.cookies
    assert "csrf_token" in r.cookies


def test_me_refreshes_session_ttl(
    gateway_admin_client: TestClient, session_redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SESSION_TTL_SECONDS", "43200")
    r = _login(gateway_admin_client)
    session_id = r.cookies.get("session")
    assert session_id

    key = f"sess:{session_id}"
    session_redis._expiry[key] = time.monotonic() + 100
    ttl_before = asyncio.run(session_redis.ttl(key))
    assert ttl_before <= 100

    me = gateway_admin_client.get("/api/v1/admin/auth/me", cookies={"session": session_id})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "admin@test.local"

    ttl_after = asyncio.run(session_redis.ttl(key))
    assert ttl_after > ttl_before


def test_logout_clears_session(gateway_admin_client: TestClient, session_redis) -> None:
    r = _login(gateway_admin_client)
    session_id = r.cookies.get("session")
    assert session_id

    out = gateway_admin_client.post("/api/v1/admin/auth/logout", cookies={"session": session_id})
    assert out.status_code == 200
    assert out.json().get("ok") is True

    raw = asyncio.run(session_redis.get(f"sess:{session_id}"))
    assert raw is None

    me = gateway_admin_client.get("/api/v1/admin/auth/me", cookies={"session": session_id})
    assert me.status_code == 401


def test_ip_rate_limit_429(gateway_admin_client: TestClient, session_redis) -> None:
    from core.admin_auth import RL_IP_PREFIX

    ip = "testclient"
    session_redis._values[f"{RL_IP_PREFIX}{ip}"] = "101"
    session_redis._expiry[f"{RL_IP_PREFIX}{ip}"] = time.monotonic() + 60

    r = _login(gateway_admin_client)
    assert r.status_code == 429


def test_login_delay_after_failures(
    gateway_admin_client: TestClient, session_redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.admin_auth import RL_EMAIL_PREFIX

    email = "admin@test.local"
    session_redis._values[f"{RL_EMAIL_PREFIX}{email}"] = "10"
    session_redis._expiry[f"{RL_EMAIL_PREFIX}{email}"] = time.monotonic() + 86400

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("core.admin_auth.asyncio.sleep", fake_sleep)

    r = gateway_admin_client.post(
        "/api/v1/admin/auth/login",
        json={"email": email, "password": "wrongpass1"},
    )
    assert r.status_code == 401
    assert sleeps and sleeps[0] == 5
