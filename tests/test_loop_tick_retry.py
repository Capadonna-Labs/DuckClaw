"""A gateway restart mid-tick ("Server disconnected") is retried once instead of losing the tick."""

import asyncio

import httpx

from duckclaw.commands import loop


class _Resp:
    status_code = 200
    text = "ok"


def _client_factory(outcomes):
    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            out = outcomes.pop(0)
            if isinstance(out, Exception):
                raise out
            return out

    return _Client


def _tick():
    return asyncio.run(
        loop.post_loop_self_tick_async(chat_id="admin-conv-abc", tenant_id="t", worker_id="w", message="m")
    )


def test_retries_once_after_gateway_restart(monkeypatch):
    monkeypatch.setattr(loop, "LOOP_SELF_RESTART_RETRY_S", 0)
    outcomes = [httpx.RemoteProtocolError("Server disconnected"), _Resp()]
    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(outcomes))
    assert _tick()["ok"] is True


def test_timeout_error_keeps_exception_type(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", _client_factory([httpx.ReadTimeout("")]))
    res = _tick()
    assert res["ok"] is False and res["error"].startswith("ReadTimeout")
