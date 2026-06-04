"""Tests for cooperative admin chat cancellation (Redis flag)."""

from __future__ import annotations

import pytest


def test_chat_cancel_redis_key() -> None:
    from duckclaw.graphs.chat_cancel import chat_cancel_redis_key

    assert chat_cancel_redis_key("admin-conv-abc").startswith("duckclaw:chat_cancel:")


def test_raise_if_chat_cancelled_when_flag_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs import chat_cancel as cc
    from duckclaw.graphs.chat_cancel import ChatCancelledError, raise_if_chat_cancelled

    monkeypatch.setattr(cc, "is_chat_cancel_requested", lambda _cid: True)
    with pytest.raises(ChatCancelledError):
        raise_if_chat_cancelled("admin-conv-test")


def test_raise_if_chat_cancelled_when_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs import chat_cancel as cc
    from duckclaw.graphs.chat_cancel import raise_if_chat_cancelled

    monkeypatch.setattr(cc, "is_chat_cancel_requested", lambda _cid: False)
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
