from __future__ import annotations

from typing import Any, Dict

import types

import duckclaw
from duckclaw import DuckClaw

from duckclaw.forge.skills import outbound_messaging


class DummyDB:
    def __init__(self) -> None:
        self.executed: list[Dict[str, Any]] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.executed.append({"sql": sql, "params": params})


def test_send_proactive_message_uses_webhook(monkeypatch: Any) -> None:
    calls: list[Dict[str, Any]] = []

    def fake_post(url: str, json: Dict[str, Any], headers: Dict[str, Any], timeout: int) -> None:  # noqa: ARG002
        calls.append({"url": url, "json": json, "headers": headers})

    dummy_db = DummyDB()

    def fake_get_db() -> DuckClaw:
        return dummy_db  # type: ignore[return-value]

    monkeypatch.setenv("N8N_OUTBOUND_WEBHOOK_URL", "https://example.test/webhook")
    monkeypatch.setenv("N8N_AUTH_KEY", "secret")
    monkeypatch.setattr(outbound_messaging, "httpx", types.SimpleNamespace(post=fake_post))
    monkeypatch.setattr(outbound_messaging, "get_db", fake_get_db)
    monkeypatch.setattr(outbound_messaging, "append_task_audit", lambda *args, **kwargs: None)  # noqa: ARG005

    result = outbound_messaging.send_proactive_message.invoke(  # type: ignore[attr-defined]
        {"chat_id": "12345", "message": "Alerta de prueba"}
    )

    assert "exitosamente" in result
    assert calls
    sent = calls[0]
    assert sent["json"]["chat_id"] == "12345"
    assert sent["json"]["text"] == "Alerta de prueba"
    assert sent["headers"]["X-DuckClaw-Secret"] == "secret"

