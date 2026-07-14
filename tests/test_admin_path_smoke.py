"""Unit tests para duckops.admin_path_smoke (cliente httpx mockeado)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from duckops.admin_path_smoke import run_admin_path_smoke


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


def test_admin_path_smoke_happy_path(monkeypatch) -> None:
    client = MagicMock()

    def _post(url: str, **kwargs):
        if url.endswith("/auth/login"):
            return _FakeResponse(200, {"user": {"email": "admin@test.local"}})
        if url.endswith("/playground/chat"):
            return _FakeResponse(200, {"ok": True, "response": "path-smoke"})
        raise AssertionError(url)

    def _get(url: str, **kwargs):
        if url.endswith("/playground/config"):
            return _FakeResponse(
                200,
                {
                    "llm": {"provider": "deepseek", "model": "deepseek-chat"},
                    "llm_gap": None,
                    "selected_worker_id": "default",
                },
            )
        raise AssertionError(url)

    client.post.side_effect = _post
    client.get.side_effect = _get

    class _ClientCtx:
        def __enter__(self):
            return client

        def __exit__(self, *_exc):
            return False

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _ClientCtx())

    checks = run_admin_path_smoke(
        base_url="http://127.0.0.1:8000",
        admin_email="admin@test.local",
        admin_password="secret123",
        admin_api_key="key",
    )
    by_name = {row.name: row for row in checks}
    assert by_name["Smoke admin login"].ok
    assert by_name["Smoke playground config"].ok
    assert by_name["Smoke playground chat"].ok


def test_admin_path_smoke_skips_chat_when_llm_gap(monkeypatch) -> None:
    client = MagicMock()
    client.post.return_value = _FakeResponse(200, {"user": {"email": "a@test.local"}})
    client.get.return_value = _FakeResponse(
        200,
        {
            "llm": {"provider": "deepseek", "model": ""},
            "llm_gap": {"message": "Falta API key"},
        },
    )

    class _ClientCtx:
        def __enter__(self):
            return client

        def __exit__(self, *_exc):
            return False

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _ClientCtx())

    checks = run_admin_path_smoke(
        base_url="http://127.0.0.1:8000",
        admin_email="a@test.local",
        admin_password="x" * 8,
        admin_api_key="key",
    )
    chat = [row for row in checks if row.name == "Smoke playground chat"][0]
    assert chat.ok is False
    assert client.post.call_count == 1
