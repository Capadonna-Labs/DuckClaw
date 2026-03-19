"""Tests for DuckClaw API Gateway (microservicio services/api-gateway)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Set auth key before app loads so middleware accepts test requests
os.environ.setdefault("DUCKCLAW_TAILSCALE_AUTH_KEY", "test-key-for-tests")

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

# Cargar app del microservicio services/api-gateway
REPO_ROOT = Path(__file__).resolve().parent.parent
API_GATEWAY_DIR = REPO_ROOT / "services" / "api-gateway"
if str(API_GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(API_GATEWAY_DIR))
import main as gateway_main
app = gateway_main.app

_AUTH_HEADERS = {"X-Tailscale-Auth-Key": "test-key-for-tests"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers=_AUTH_HEADERS)


def test_root(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data.get("service") == "DuckClaw API Gateway"
    assert "endpoints" in data


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_system_health(client: TestClient) -> None:
    r = client.get("/api/v1/system/health")
    assert r.status_code == 200
    data = r.json()
    assert "tailscale" in data
    assert "duckdb" in data
    assert "mlx" in data


def test_homeostasis_status(client: TestClient) -> None:
    r = client.get("/api/v1/homeostasis/status")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_homeostasis_ask_task(client: TestClient) -> None:
    r = client.post("/api/v1/homeostasis/ask_task", json={})
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("trigger") == "timer"


def test_homeostasis_ask_task_with_objectives(client: TestClient) -> None:
    r = client.post(
        "/api/v1/homeostasis/ask_task",
        json={"suggested_objectives": ["Aumentar ventas", "Disminuir tiempo de respuesta"]},
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_resolve_chat_session_id_from_query_string() -> None:
    from core.models import ChatRequest
    import main as gateway_main

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/agent/chat",
        "headers": [],
        "query_string": b"session_id=1726618406",
    }
    req = Request(scope)
    body = ChatRequest.model_validate({"message": "hi"})
    session_id, source = gateway_main._resolve_chat_session_id(body, req)
    assert session_id == "1726618406"
    assert source == "query.session_id"


def test_resolve_chat_session_id_prefers_body_over_query() -> None:
    from core.models import ChatRequest
    import main as gateway_main

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/agent/chat",
        "headers": [],
        "query_string": b"chat_id=from_query",
    }
    req = Request(scope)
    body = ChatRequest.model_validate({"message": "hi", "chat_id": "from_body"})
    session_id, source = gateway_main._resolve_chat_session_id(body, req)
    assert session_id == "from_body"
    assert source == "body.chat_id"


def test_chat_request_aliases_map_to_chat_id() -> None:
    """session_id/thread_id/chatId deben poblar chat_id (misma sesión que /sandbox)."""
    from core.models import ChatRequest

    m1 = ChatRequest.model_validate({"message": "x", "session_id": "1726618406"})
    assert m1.chat_id == "1726618406"
    m2 = ChatRequest.model_validate({"message": "x", "thread_id": "t1"})
    assert m2.chat_id == "t1"
    m3 = ChatRequest.model_validate({"message": "x", "chatId": "c1"})
    assert m3.chat_id == "c1"
    m4 = ChatRequest.model_validate({"message": "x", "chat_id": "  trim "})
    assert m4.chat_id == "trim"


def test_chat_request_username_coerces_dict_to_str() -> None:
    from core.models import ChatRequest

    payload = {
        "message": "x",
        "chat_id": "c1",
        "user_id": "u1",
        "username": {"username": "juan_telegram"},
    }
    m = ChatRequest.model_validate(payload)
    assert m.username == "juan_telegram"


def test_clean_agent_response_removes_menus() -> None:
    raw = (
        "Tu saldo total es 1.234.567 COP.\n\n"
        "¿Qué te gustaría hacer ahora?\n"
        "1. Ver resumen financiero\n"
        "2. Registrar un gasto\n"
        "- 📊 Resumen financiero\n"
        "- Otras opciones..."
    )
    cleaned = gateway_main.clean_agent_response(raw)
    assert "¿Qué te gustaría hacer ahora?" not in cleaned
    assert "Resumen financiero" not in cleaned
    assert "Tu saldo total es 1.234.567 COP." in cleaned


def test_agent_history_requires_session(client: TestClient) -> None:
    r = client.get("/api/v1/agent/finanz/history?session_id=s1")
    assert r.status_code == 200
    data = r.json()
    assert "history" in data
    assert data.get("worker_id") == "finanz"


def test_agent_workers_list(client: TestClient) -> None:
    r = client.get("/api/v1/agent/workers")
    assert r.status_code == 200
    data = r.json()
    assert "workers" in data
    assert isinstance(data["workers"], list)
    assert "finanz" in data["workers"]


def test_forget_command_via_api_succeeds(client: TestClient) -> None:
    """POST /forget with session_id='default' succeeds (fix for API gateway bug)."""
    r = client.post(
        "/api/v1/agent/finanz/chat",
        json={
            "message": "/forget",
            "chat_id": "default",
            "user_id": "1726618406",
            "username": "admin",
            "chat_type": "private",
            "history": [],
            "stream": False,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "response" in data
    assert "✅" in data["response"] or "Historial borrado" in data["response"]
