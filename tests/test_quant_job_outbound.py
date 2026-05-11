"""Tests for scripts/quant/_job_common outbound Telegram (n8n webhook)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest


def test_send_quant_alert_message_skip_no_chat(monkeypatch: Any, capsys: Any) -> None:
    from scripts.quant import _job_common as jc

    called: list[Any] = []

    def _fake_post(*_a: Any, **_k: Any) -> None:
        called.append(True)

    monkeypatch.setenv("N8N_OUTBOUND_WEBHOOK_URL", "https://example.invalid/webhook")
    monkeypatch.delenv("DUCKCLAW_QUANT_ALERT_CHAT_ID", raising=False)
    monkeypatch.delenv("DUCKCLAW_OWNER_ID", raising=False)
    monkeypatch.setattr(jc, "httpx", SimpleNamespace(post=_fake_post))

    ok = jc.send_quant_alert_message("hello")
    assert ok is False
    assert called == []
    err = capsys.readouterr().err
    assert "chat" in err.lower()


def test_send_quant_alert_message_posts_with_user_id(monkeypatch: Any) -> None:
    from scripts.quant import _job_common as jc

    captured: dict[str, Any] = {}

    class _Resp:
        is_success = True

    def _fake_post(url: str, json: dict[str, Any], **_k: Any) -> _Resp:
        captured["url"] = url
        captured["json"] = json
        return _Resp()

    monkeypatch.setenv("N8N_OUTBOUND_WEBHOOK_URL", "https://n8n.example/hook")
    monkeypatch.setenv("DUCKCLAW_QUANT_ALERT_CHAT_ID", "123456")
    monkeypatch.delenv("N8N_AUTH_KEY", raising=False)
    monkeypatch.setattr(jc, "httpx", SimpleNamespace(post=_fake_post))

    ok = jc.send_quant_alert_message("Line1")
    assert ok is True
    assert captured["url"] == "https://n8n.example/hook"
    body = captured["json"]
    assert body["chat_id"] == "123456"
    assert body["user_id"] == "123456"
    assert body["parse_mode"] == "HTML"
    assert body["text"] == "Line1"


def test_quant_outbound_env_ready_false_without_url(monkeypatch: Any) -> None:
    from scripts.quant import _job_common as jc

    monkeypatch.delenv("N8N_OUTBOUND_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES", "")
    monkeypatch.setenv("DUCKCLAW_QUANT_ALERT_CHAT_ID", "1")
    ok, reason = jc.quant_outbound_env_ready()
    assert ok is False
    assert "no_webhook" in reason or "bot_token" in reason


@pytest.mark.parametrize(
    "status,expect_ok",
    [(200, True), (201, True), (500, False)],
)
def test_send_quant_alert_message_http_status(
    monkeypatch: Any, capsys: Any, status: int, expect_ok: bool
) -> None:
    from scripts.quant import _job_common as jc

    class _Resp:
        def __init__(self, code: int) -> None:
            self.status_code = code
            self.text = "err body"
            self.is_success = 200 <= code < 300

    def _fake_post(*_a: Any, **_k: Any) -> _Resp:
        return _Resp(status)

    monkeypatch.setenv("N8N_OUTBOUND_WEBHOOK_URL", "https://n8n.example/hook")
    monkeypatch.setenv("DUCKCLAW_QUANT_ALERT_CHAT_ID", "99")
    monkeypatch.setattr(jc, "httpx", SimpleNamespace(post=_fake_post))
    monkeypatch.setattr(jc, "_send_quant_alert_native_bot_api", lambda *_a, **_k: False)
    monkeypatch.setattr(jc, "_quant_native_bot_token", lambda: "")

    ok = jc.send_quant_alert_message("x")
    assert ok is expect_ok
    if not expect_ok:
        assert "500" in capsys.readouterr().err
