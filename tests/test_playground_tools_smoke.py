"""Tests para playground_tools_smoke."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from duckops.playground_tools_smoke import (
    _response_suggests_read_sql,
    run_playground_tools_smoke,
)


def test_response_suggests_read_sql() -> None:
    assert _response_suggests_read_sql("8742")
    assert _response_suggests_read_sql("El resultado es 8742")
    assert not _response_suggests_read_sql("default 1")


def test_playground_tools_smoke_happy_path(monkeypatch) -> None:
    client = MagicMock()

    def _post(url: str, **kwargs):
        if url.endswith("/auth/login"):
            return _resp(200, {"user": {"email": "a@test.local"}})
        if url.endswith("/playground/chat"):
            return _resp(200, {"ok": True, "response": "8742"})
        raise AssertionError(url)

    def _get(url: str, **kwargs):
        if url.endswith("/playground/config"):
            return _resp(
                200,
                {
                    "llm": {"provider": "deepseek"},
                    "selected_worker_id": "default",
                },
            )
        if url.endswith("/capabilities"):
            return _resp(
                200,
                {
                    "tools_runtime": ["read_sql", "inspect_schema", "run_sandbox"],
                    "gaps": [],
                },
            )
        raise AssertionError(url)

    client.post.side_effect = _post
    client.get.side_effect = _get

    class _Ctx:
        def __enter__(self):
            return client

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _Ctx())

    checks = run_playground_tools_smoke(
        base_url="http://127.0.0.1:8000",
        admin_email="a@test.local",
        admin_password="secret123",
        admin_api_key="key",
    )
    by_name = {row.name: row for row in checks}
    assert by_name["Tools smoke capabilities"].ok
    assert by_name["Tools smoke read_sql turn"].ok


def _resp(status: int, payload: dict):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    r.text = ""
    return r
