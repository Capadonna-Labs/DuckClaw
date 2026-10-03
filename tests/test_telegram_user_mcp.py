"""Telegram user-account MCP: policy + server-side enforcement (no network)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from duckclaw_telegram_mcp.user_policy import (
    HourlyRateLimiter,
    entity_keys,
    load_policy,
    parse_allowlist,
)


def test_parse_allowlist_normalizes_and_detects_wildcard() -> None:
    assert parse_allowlist(" @Canal_Señales, -100123 ,me") == (
        False,
        frozenset({"canal_señales", "-100123", "me"}),
    )
    assert parse_allowlist("*, x")[0] is True
    assert parse_allowlist(None) == (False, frozenset())


def test_policy_defaults_are_closed_and_send_is_draft() -> None:
    policy = load_policy({})
    assert policy.can_read({"123"}) is False
    assert policy.can_send({"123"}) is False
    assert policy.send_mode == "draft"


def test_policy_matches_by_id_username_or_me() -> None:
    policy = load_policy(
        {
            "TELEGRAM_USER_READ_ALLOW": "-100555,@quantsignals,me",
            "TELEGRAM_USER_SEND_ALLOW": "me",
            "TELEGRAM_USER_SEND_MODE": "direct",
        }
    )
    assert policy.can_read(entity_keys(-100555)) is True
    assert policy.can_read(entity_keys(-100999, "QuantSignals")) is True
    assert policy.can_read(entity_keys(42)) is False
    assert policy.can_send(entity_keys(42, is_self=True)) is True
    assert policy.can_send(entity_keys(-100555)) is False
    assert policy.send_mode == "direct"


def test_rate_limiter_rolls_over_after_an_hour() -> None:
    rl = HourlyRateLimiter(2)
    assert rl.allow(0) and rl.allow(1)
    assert rl.allow(2) is False
    assert rl.allow(3601) is True


# --- server-side enforcement with a fake Telethon client -------------------------

pytest.importorskip("telethon")

from duckclaw_telegram_mcp import user_server  # noqa: E402
from duckclaw_telegram_mcp.user_server import TelegramUserService  # noqa: E402


class _FakeClient:
    def __init__(self, entities: dict) -> None:
        self.entities = entities
        self.sent: list = []
        self.drafts: list = []

    async def get_entity(self, ref):
        return self.entities[ref]

    async def get_input_entity(self, entity):
        return entity

    async def send_message(self, entity, text):
        self.sent.append((entity.id, text))
        return SimpleNamespace(id=777)

    async def __call__(self, request):
        self.drafts.append(request)

    def iter_dialogs(self, limit=200):
        async def _gen():
            for ent in self.entities.values():
                yield SimpleNamespace(
                    entity=ent, is_user=True, is_group=False, unread_count=0
                )

        return _gen()


def _user(uid: int, username: str | None = None, is_self: bool = False):
    from telethon.tl.types import User

    return User(id=uid, username=username, first_name=f"u{uid}", is_self=is_self)


def _service(env: dict, client: _FakeClient) -> TelegramUserService:
    svc = TelegramUserService(load_policy(env))

    async def _client():
        return client

    svc.client = _client  # type: ignore[method-assign]
    return svc


def _run(coro):
    return json.loads(asyncio.run(coro))


def test_send_is_denied_outside_send_allowlist() -> None:
    alice = _user(10, "alice")
    client = _FakeClient({"@alice": alice})
    svc = _service({"TELEGRAM_USER_READ_ALLOW": "*"}, client)
    out = _run(svc.send_message("alice", "hola"))
    assert out["ok"] is False
    assert client.sent == [] and client.drafts == []


def test_send_defaults_to_draft_not_direct(monkeypatch) -> None:
    alice = _user(10, "alice")
    client = _FakeClient({"@alice": alice})
    svc = _service({"TELEGRAM_USER_SEND_ALLOW": "@alice"}, client)
    out = _run(svc.send_message("@alice", "borrador"))
    assert out["ok"] is True and out["mode"] == "draft"
    assert client.sent == []
    assert len(client.drafts) == 1


def test_direct_mode_sends_and_rate_limit_applies() -> None:
    alice = _user(10, "alice")
    client = _FakeClient({"@alice": alice})
    svc = _service(
        {
            "TELEGRAM_USER_SEND_ALLOW": "alice",
            "TELEGRAM_USER_SEND_MODE": "direct",
            "TELEGRAM_USER_SEND_PER_HOUR": "1",
        },
        client,
    )
    assert _run(svc.send_message("alice", "uno"))["mode"] == "direct"
    second = _run(svc.send_message("alice", "dos"))
    assert second["ok"] is False and "Límite" in second["error"]
    assert client.sent == [(10, "uno")]


def test_read_denied_outside_read_allowlist() -> None:
    bob = _user(20, "bob")
    client = _FakeClient({"@bob": bob})
    svc = _service({"TELEGRAM_USER_READ_ALLOW": "@alice"}, client)
    out = _run(svc.read_messages("bob"))
    assert out["ok"] is False


def test_list_chats_hides_chats_outside_read_allowlist() -> None:
    client = _FakeClient({"@alice": _user(10, "alice"), "@bob": _user(20, "bob")})
    svc = _service({"TELEGRAM_USER_READ_ALLOW": "alice", "TELEGRAM_USER_SEND_ALLOW": "alice"}, client)
    out = _run(svc.list_chats())
    assert [c["username"] for c in out["chats"]] == ["alice"]
    assert out["chats"][0]["can_send"] is True


def test_parse_chat_ref() -> None:
    assert user_server._parse_chat_ref("me") == "me"
    assert user_server._parse_chat_ref("-100123") == -100123
    assert user_server._parse_chat_ref("alice") == "@alice"
    with pytest.raises(ValueError):
        user_server._parse_chat_ref("  ")


def test_mark_read_follows_read_allowlist() -> None:
    alice, bob = _user(10, "alice"), _user(20, "bob")
    client = _FakeClient({"@alice": alice, "@bob": bob})
    acks: list = []

    async def _ack(entity, max_id=None):
        acks.append((entity.id, max_id))

    client.send_read_acknowledge = _ack
    svc = _service({"TELEGRAM_USER_READ_ALLOW": "@alice"}, client)
    assert _run(svc.mark_read("bob"))["ok"] is False
    out = _run(svc.mark_read("alice"))
    assert out["ok"] is True and out["marked_read_up_to"] == "all"
    assert _run(svc.mark_read("alice", 55))["marked_read_up_to"] == 55
    assert acks == [(10, None), (10, 55)]
