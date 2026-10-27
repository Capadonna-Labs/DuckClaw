"""Gateway guards for public callers: body-size cap (413) and per-IP rate (429); trusted networks are exempt."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_gw = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))

from core import middleware  # noqa: E402


def _client(host: str) -> TestClient:
    app = FastAPI()
    app.middleware("http")(middleware.request_limits_middleware)

    @app.post("/echo")
    async def echo() -> dict:
        return {"ok": True}

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True}

    return TestClient(app, client=(host, 50000))


@pytest.fixture(autouse=True)
def _fresh_windows(monkeypatch) -> None:
    middleware._RATE_WINDOWS.clear()
    monkeypatch.delenv("DUCKCLAW_MAX_BODY_MB", raising=False)
    monkeypatch.delenv("DUCKCLAW_RATE_LIMIT_PER_MIN", raising=False)


def test_public_caller_over_the_body_cap_gets_413(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_MAX_BODY_MB", "1")
    c = _client("8.8.8.8")
    assert c.post("/echo", content=b"x" * 1024).status_code == 200
    assert c.post("/echo", content=b"x" * (1024 * 1024 + 1)).status_code == 413


def test_public_caller_over_the_rate_gets_429_with_retry_after(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_RATE_LIMIT_PER_MIN", "3")
    c = _client("8.8.8.8")
    assert [c.post("/echo").status_code for _ in range(4)] == [200, 200, 200, 429]
    assert c.post("/echo").headers["retry-after"] == "60"
    assert c.get("/health").status_code == 200                       # health checks are never limited
    assert _client("1.1.1.1").post("/echo").status_code == 200        # another IP has its own window


@pytest.mark.parametrize("host", ["127.0.0.1", "10.0.0.5", "172.18.0.3", "192.168.1.9", "100.79.185.46", "testclient"])
def test_loopback_private_and_tailscale_callers_are_never_limited(monkeypatch, host) -> None:
    monkeypatch.setenv("DUCKCLAW_RATE_LIMIT_PER_MIN", "1")
    monkeypatch.setenv("DUCKCLAW_MAX_BODY_MB", "1")
    c = _client(host)
    assert [c.post("/echo").status_code for _ in range(3)] == [200, 200, 200]
    assert c.post("/echo", content=b"x" * (1024 * 1024 + 1)).status_code == 200


def test_zero_turns_each_guard_off(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_RATE_LIMIT_PER_MIN", "0")
    monkeypatch.setenv("DUCKCLAW_MAX_BODY_MB", "0")
    c = _client("8.8.8.8")
    assert [c.post("/echo").status_code for _ in range(5)] == [200] * 5
    assert c.post("/echo", content=b"x" * (2 * 1024 * 1024)).status_code == 200


def test_limits_run_before_auth_in_the_gateway_chain() -> None:
    src = (_gw / "core" / "middleware.py").read_text(encoding="utf-8")
    reg = src.split("def register_gateway_middleware")[1]
    assert reg.index("tailscale_auth_middleware") < reg.index("request_limits_middleware") < reg.index("telegram_http_ingress_probe_middleware")


def _cors_app() -> TestClient:
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI()
    app.add_middleware(CORSMiddleware, **middleware.cors_settings())

    @app.get("/x")
    async def x() -> dict:
        return {"ok": True}

    return TestClient(app)


def test_cors_defaults_allow_only_local_origins_with_credentials(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_CORS_ORIGINS", raising=False)
    c = _cors_app()
    ok = c.get("/x", headers={"Origin": "http://localhost:3001"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:3001" and ok.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in c.get("/x", headers={"Origin": "https://evil.example"}).headers


def test_cors_origins_come_from_the_env_list(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_CORS_ORIGINS", " https://duckclaw.tail1234.ts.net/ , http://localhost:3001 ")
    c = _cors_app()
    assert c.get("/x", headers={"Origin": "https://duckclaw.tail1234.ts.net"}).headers["access-control-allow-origin"] == "https://duckclaw.tail1234.ts.net"
    assert "access-control-allow-origin" not in c.get("/x", headers={"Origin": "http://localhost:3000"}).headers   # the list replaces the defaults


def test_cors_wildcard_is_explicit_and_never_carries_credentials(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_CORS_ORIGINS", "*")
    s = middleware.cors_settings()
    assert s["allow_origins"] == ["*"] and s["allow_credentials"] is False
    r = _cors_app().get("/x", headers={"Origin": "https://anything.example"})
    assert r.headers["access-control-allow-origin"] == "*" and "access-control-allow-credentials" not in r.headers
