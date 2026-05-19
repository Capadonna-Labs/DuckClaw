from __future__ import annotations

from typing import Any, Dict

import duckclaw
from duckclaw import DuckClaw

from duckclaw.forge.skills import outbound_messaging


class DummyDB:
    def __init__(self) -> None:
        self.executed: list[Dict[str, Any]] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.executed.append({"sql": sql, "params": params})


def test_send_proactive_message_uses_bot_api(monkeypatch: Any) -> None:
    calls: list[Dict[str, Any]] = []

    def fake_send(**kwargs: Any) -> bool:
        calls.append(kwargs)
        return True

    dummy_db = DummyDB()

    def fake_get_db() -> DuckClaw:
        return dummy_db  # type: ignore[return-value]

    monkeypatch.setattr(
        outbound_messaging,
        "effective_telegram_bot_token_outbound",
        lambda: "test-token",
    )
    monkeypatch.setattr(outbound_messaging, "send_bot_message_sync", fake_send)
    monkeypatch.setattr(outbound_messaging, "get_db", fake_get_db)
    monkeypatch.setattr(outbound_messaging, "append_task_audit", lambda *args, **kwargs: None)  # noqa: ARG005

    result = outbound_messaging.send_proactive_message.invoke(  # type: ignore[attr-defined]
        {"chat_id": "12345", "message": "Alerta de prueba"}
    )

    assert "exitosamente" in result
    assert calls
    assert calls[0]["chat_id"] == "12345"
    assert calls[0]["bot_token"] == "test-token"
