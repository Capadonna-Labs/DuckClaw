"""Tests for cooperative admin chat cancellation (Redis flag) and graph interrupt."""

from __future__ import annotations

import pytest


def test_chat_cancel_redis_key() -> None:
    from duckclaw.graphs.chat_cancel import chat_cancel_redis_key

    assert chat_cancel_redis_key("admin-conv-abc").startswith("duckclaw:chat_cancel:")


def test_raise_if_chat_cancelled_when_flag_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs import chat_cancel as cc
    from duckclaw.graphs.chat_cancel import ChatCancelledError, raise_if_chat_cancelled

    monkeypatch.setattr(cc, "is_chat_cancel_requested", lambda _cid: True)
    monkeypatch.setattr(cc, "is_graph_interrupt_requested", lambda _cid: False)
    with pytest.raises(ChatCancelledError):
        raise_if_chat_cancelled("admin-conv-test")


def test_raise_if_chat_cancelled_when_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs import chat_cancel as cc
    from duckclaw.graphs.chat_cancel import raise_if_chat_cancelled

    monkeypatch.setattr(cc, "is_chat_cancel_requested", lambda _cid: False)
    monkeypatch.setattr(cc, "is_graph_interrupt_requested", lambda _cid: False)
    raise_if_chat_cancelled("admin-conv-test")


def test_request_chat_cancel_local_without_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs import chat_cancel as cc
    from duckclaw.graphs.chat_cancel import (
        clear_chat_cancel,
        is_chat_cancel_requested,
        request_chat_cancel,
    )

    monkeypatch.setattr(cc, "_redis_url", lambda: "")
    cid = "admin-conv-local-cancel"
    clear_chat_cancel(cid)
    assert not is_chat_cancel_requested(cid)
    assert request_chat_cancel(cid) is True
    assert is_chat_cancel_requested(cid)
    clear_chat_cancel(cid)
    assert not is_chat_cancel_requested(cid)


def test_graph_interrupt_does_not_set_chat_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wall-clock orphan stop must not look like a user SSE cancel."""
    from duckclaw.graphs import chat_cancel as cc
    from duckclaw.graphs.chat_cancel import (
        ChatCancelledError,
        clear_graph_interrupt,
        is_chat_cancel_requested,
        is_graph_interrupt_requested,
        raise_if_chat_cancelled,
        request_graph_interrupt,
    )

    monkeypatch.setattr(cc, "_redis_url", lambda: "")
    cid = "admin-conv-graph-interrupt"
    clear_graph_interrupt(cid)
    assert not is_chat_cancel_requested(cid)
    assert not is_graph_interrupt_requested(cid)
    assert request_graph_interrupt(cid) is True
    assert is_graph_interrupt_requested(cid)
    assert not is_chat_cancel_requested(cid)
    with pytest.raises(ChatCancelledError, match="Graph interrupted"):
        raise_if_chat_cancelled(cid)
    clear_graph_interrupt(cid)
    assert not is_graph_interrupt_requested(cid)


def test_invoke_timeout_uses_graph_interrupt_not_chat_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time
    from unittest.mock import MagicMock

    from duckclaw.graphs import chat_cancel as cc
    from duckclaw.workers import worker_invoke as wi

    monkeypatch.setattr(cc, "_redis_url", lambda: "")
    monkeypatch.setattr(wi, "_DELEGATE_INVOKE_TIMEOUT_SEC", 0.05)
    cid = "admin-conv-timeout-interrupt"
    cc.clear_chat_cancel(cid)
    cc.clear_graph_interrupt(cid)

    def _hang(_state, _cfg=None):
        time.sleep(2.0)
        return {"reply": "late"}

    graph = MagicMock()
    graph.invoke.side_effect = _hang

    with pytest.raises(TimeoutError, match="exceeded"):
        wi.invoke_worker_graph(graph, {}, chat_id=cid, timeout_sec=0.05)

    assert cc.is_graph_interrupt_requested(cid)
    assert not cc.is_chat_cancel_requested(cid)
    cc.clear_graph_interrupt(cid)
