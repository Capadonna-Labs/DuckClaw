"""Tests for DuckClaw API Gateway (microservicio services/api-gateway)."""

from __future__ import annotations

import json
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


def test_chat_parallel_invocations_env() -> None:
    import os

    prev = os.environ.get("DUCKCLAW_CHAT_PARALLEL_INVOCATIONS")
    try:
        os.environ["DUCKCLAW_CHAT_PARALLEL_INVOCATIONS"] = ""
        assert gateway_main._chat_parallel_invocations_enabled() is False
        os.environ["DUCKCLAW_CHAT_PARALLEL_INVOCATIONS"] = "true"
        assert gateway_main._chat_parallel_invocations_enabled() is True
    finally:
        if prev is None:
            os.environ.pop("DUCKCLAW_CHAT_PARALLEL_INVOCATIONS", None)
        else:
            os.environ["DUCKCLAW_CHAT_PARALLEL_INVOCATIONS"] = prev


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


def test_clean_agent_response_keeps_puedo_ayudarte_bi_style() -> None:
    """No borrar el cuerpo tras 'puedo ayudarte con:' (respuestas analíticas válidas)."""
    raw = (
        "Como analista BI, puedo ayudarte con:\n\n"
        "**Análisis:**\n"
        "- Ventas por región\n"
        "- Métricas de latencia"
    )
    cleaned = gateway_main.clean_agent_response(raw)
    assert "Ventas por región" in cleaned
    assert "Métricas de latencia" in cleaned


def test_clean_agent_response_keeps_body_after_cual_es_mi_tarea() -> None:
    """Regresión: DOTALL en '¿Cuál es mi tarea?' borraba todo el texto útil para Telegram."""
    raw = (
        "BI-Analyst 1\n\n"
        "¿Cuál es mi tarea?\n\n"
        "Como analista senior de BI, puedo ayudarte con:\n"
        "- Análisis de ventas\n"
        "- Métricas de rendimiento"
    )
    cleaned = gateway_main.clean_agent_response(raw)
    assert "¿Cuál es mi tarea?" not in cleaned
    assert "Análisis de ventas" in cleaned
    assert "Métricas de rendimiento" in cleaned


def test_clean_agent_response_strips_pre_tags() -> None:
    raw = "<pre>line1\nline2</pre>\n\nTexto visible"
    cleaned = gateway_main.clean_agent_response(raw)
    assert "<pre>" not in cleaned.lower()
    assert "</pre>" not in cleaned.lower()
    assert "line1" in cleaned
    assert "Texto visible" in cleaned


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


def test_effective_tenant_bi_analyst_from_pm2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_GATEWAY_TENANT_ID", raising=False)
    monkeypatch.setenv("DUCKCLAW_PM2_PROCESS_NAME", "BI-Analyst-Gateway")
    assert gateway_main._effective_tenant_id(None) == "BI-Analyst"


def test_effective_tenant_bi_analyst_from_db_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_GATEWAY_TENANT_ID", raising=False)
    monkeypatch.delenv("DUCKCLAW_PM2_PROCESS_NAME", raising=False)
    monkeypatch.setenv("DUCKCLAW_DB_PATH", "/data/bi_analyst.duckdb")
    assert gateway_main._effective_tenant_id(None) == "BI-Analyst"


def test_effective_tenant_env_overrides_bi_pm2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_GATEWAY_TENANT_ID", "acme-corp")
    monkeypatch.setenv("DUCKCLAW_PM2_PROCESS_NAME", "BI-Analyst-Gateway")
    assert gateway_main._effective_tenant_id(None) == "acme-corp"


def test_split_plain_text_for_telegram_reply() -> None:
    assert gateway_main._split_plain_text_for_telegram_reply("", 80) == [""]
    raw = "a" * 200
    # el splitter impone mínimo 64 caracteres por trozo
    parts = gateway_main._split_plain_text_for_telegram_reply(raw, 80)
    assert "".join(parts) == raw
    assert all(len(p) <= 80 for p in parts)
    with_nl = "l1\n" + "b" * 30 + "\nl3"
    p2 = gateway_main._split_plain_text_for_telegram_reply(with_nl, 80)
    assert "".join(p2) == with_nl


def test_plain_subchunks_for_telegram_budget_splits_when_escape_grows() -> None:
    def fake_safe(s: str) -> str:
        # longitud artificial >> límite Telegram para forzar subdivisión
        return "x" * (len(s) * 1100)

    tiny = gateway_main._plain_subchunks_for_telegram_budget("abcd", fake_safe)
    assert len(tiny) > 1
    assert "".join(tiny) == "abcd"


def test_webhook_outbound_chat_reply_sync_posts_json(monkeypatch: pytest.MonkeyPatch) -> None:
    posted: list[dict[str, str]] = []
    monkeypatch.setenv("DUCKCLAW_TELEGRAM_OUTBOUND_VIA", "n8n")
    monkeypatch.setenv("N8N_OUTBOUND_WEBHOOK_URL", "https://example.test/webhook")

    class _Resp:
        def read(self) -> bytes:
            return b"ok"

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    def fake_urlopen(req: object, timeout: int = 30) -> _Resp:
        posted.append(json.loads(req.data.decode("utf-8")))  # type: ignore[attr-defined]
        return _Resp()

    monkeypatch.setattr(gateway_main._url_request, "urlopen", fake_urlopen)
    gateway_main._webhook_outbound_chat_reply_sync(
        chat_id="1726618406",
        user_id="1726618406",
        text="hola",
    )
    assert len(posted) == 1
    assert posted[0]["chat_id"] == "1726618406"
    assert posted[0]["user_id"] == "1726618406"
    assert posted[0]["text"] == "hola"
    assert posted[0].get("parse_mode") == "HTML"


def test_pm2_json_lists_gateways_with_explicit_db_path() -> None:
    from duckclaw.pm2_gateway_db import pm2_gateway_names_with_explicit_db_path

    names = pm2_gateway_names_with_explicit_db_path()
    assert "SIATA-Gateway" in names
    assert "BI-Analyst-Gateway" in names


def test_dedicated_gateway_vault_matches_pm2_db_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Evita que fly/manager abran finanzdb1 cuando el proceso es un gateway con DB propia."""
    dbf = tmp_path / "dedicated.duckdb"
    monkeypatch.setenv("DUCKCLAW_PM2_PROCESS_NAME", "SIATA-Gateway")
    monkeypatch.setenv("DUCKCLAW_DB_PATH", str(dbf))
    assert gateway_main._dedicated_gateway_vault_db_path() == str(dbf.resolve())


def test_dedicated_gateway_vault_unknown_pm2_name_returns_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DUCKCLAW_PM2_PROCESS_NAME", "Not-In-Pm2-Json-XYZ")
    monkeypatch.setenv("DUCKCLAW_DB_PATH", str(tmp_path / "x.duckdb"))
    assert gateway_main._dedicated_gateway_vault_db_path() is None


def test_dedicated_gateway_vault_uses_matched_app_when_pm2_alias_differs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """PM2 puede llamar el proceso distinto al ``name`` del JSON; el match por puerto fija MATCHED."""
    dbf = tmp_path / "bi.duckdb"
    monkeypatch.setenv("DUCKCLAW_PM2_PROCESS_NAME", "BIAnalyst-Gateway")
    monkeypatch.setenv("DUCKCLAW_PM2_MATCHED_APP_NAME", "BI-Analyst-Gateway")
    monkeypatch.setenv("DUCKCLAW_DB_PATH", str(dbf))
    assert gateway_main._dedicated_gateway_vault_db_path() == str(dbf.resolve())
