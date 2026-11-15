"""Emoji reactions on chat messages: storage keys, attach to history, and the note the agent reads."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api-gateway"))

from core import chat_reactions as cr  # noqa: E402


class FakeRedis:
    def __init__(self) -> None:
        self.h: dict[str, dict[str, str]] = {}

    async def hset(self, key, field, value):
        self.h.setdefault(key, {})[field] = value

    async def hdel(self, key, field):
        self.h.get(key, {}).pop(field, None)

    async def expire(self, key, ttl):
        return True

    async def hgetall(self, key):
        return dict(self.h.get(key, {}))


def test_emoji_must_be_a_pictograph() -> None:
    assert cr.valid_emoji(" 👍 ") == "👍" and cr.valid_emoji("1️⃣") == "1️⃣"
    assert cr.valid_emoji("ok") is None and cr.valid_emoji("") is None and cr.valid_emoji("👍" * 20) is None


def test_key_follows_role_and_text_not_whitespace() -> None:
    assert cr.msg_key("user", " hola ") == cr.msg_key("user", "hola")
    assert cr.msg_key("user", "hola") != cr.msg_key("assistant", "hola") and cr.msg_key("system", "x") is None and cr.msg_key("user", "  ") is None


def test_react_toggle_attach_and_agent_note() -> None:
    r = FakeRedis()
    run = asyncio.run
    assert run(cr.set_reaction(r, "t", "s", "assistant", "El plan es X", "user", "👍"))
    assert run(cr.set_reaction(r, "t", "s", "user", "Hazlo", "agent", "🫡"))
    assert not run(cr.set_reaction(r, "t", "s", "user", "Hazlo", "robot", "🫡")) and not run(cr.set_reaction(None, "t", "s", "user", "Hazlo", "user", "👍"))
    got = run(cr.load_reactions(r, "t", "s"))
    msgs = [{"role": "user", "content": "Hazlo"}, {"role": "assistant", "content": "El plan es X"}, {"role": "assistant", "content": "otro"}]
    cr.attach_reactions(msgs, got)
    assert msgs[0]["reactions"] == [{"emoji": "🫡", "by": "agent"}] and msgs[1]["reactions"] == [{"emoji": "👍", "by": "user"}] and "reactions" not in msgs[2]
    noted = cr.annotate_history_for_model(msgs, got)
    assert noted[1]["content"].endswith("reaccionó a este mensaje con 👍]") and noted[0]["content"] == "Hazlo" and msgs[1]["content"] == "El plan es X"   # copy: the stored text is intact
    assert run(cr.set_reaction(r, "t", "s", "assistant", "El plan es X", "user", None))   # same emoji tap again / clear removes it
    assert cr.annotate_history_for_model(msgs, run(cr.load_reactions(r, "t", "s")))[1]["content"] == "El plan es X"


def test_agent_reaction_queued_by_the_tool_lands_on_the_users_message() -> None:
    import json

    from duckclaw.forge.skills.react_to_message_bridge import pending_reaction_key, react_to_message_impl

    assert json.loads(react_to_message_impl("ok"))["error"] == "invalid_emoji"   # a word is not a reaction
    r = FakeRedis()
    r.kv = {pending_reaction_key("t", "s"): "🫡"}

    async def get(k):
        return r.kv.get(k)

    async def delete(k):
        r.kv.pop(k, None)

    r.get, r.delete = get, delete
    asyncio.run(cr.apply_pending_agent_reaction(r, "t", "s", "Hazlo"))
    assert asyncio.run(cr.load_reactions(r, "t", "s"))[cr.msg_key("user", "Hazlo")] == [{"emoji": "🫡", "by": "agent"}] and not r.kv   # applied once, then cleared


def test_interim_messages_are_validated_and_stored_before_the_final_answer() -> None:
    import json

    from duckclaw.forge.skills.react_to_message_bridge import pending_interim_key, send_interim_message_impl

    assert json.loads(send_interim_message_impl("   "))["error"] == "empty_text"
    assert json.loads(send_interim_message_impl("x" * 400))["error"] == "too_long"
    assert json.loads(send_interim_message_impl("Reviso eso"))["error"] == "chat_unavailable"   # no chat context in a unit test

    class R:
        def __init__(self) -> None:
            self.l = ["Reviso eso y te cuento", "  Ya casi  "]

        async def lrange(self, k, a, b):
            return list(self.l) if k == pending_interim_key("t", "s") else []

        async def delete(self, k):
            self.l = []

    r = R()
    got = asyncio.run(cr.pop_pending_interim_messages(r, "t", "s"))
    assert [g["content"] for g in got] == ["Reviso eso y te cuento", "Ya casi"] and all(g["role"] == "assistant" for g in got)
    assert asyncio.run(cr.pop_pending_interim_messages(r, "t", "s")) == [] and asyncio.run(cr.pop_pending_interim_messages(None, "t", "s")) == []


def test_auto_ack_fires_once_per_turn_on_the_first_real_tool(monkeypatch) -> None:
    from duckclaw.forge.skills import react_to_message_bridge as b

    store: dict = {}
    sent: list = []

    class R:
        def set(self, k, v, nx=False, ex=None):
            if nx and k in store:
                return None
            store[k] = v
            return True

        def rpush(self, k, v):
            store.setdefault(k, []).append(v)

        def expire(self, k, t):
            return True

        def close(self):
            pass

    import redis

    monkeypatch.setattr(redis, "from_url", lambda *a, **k: R())
    monkeypatch.setattr("duckclaw.forge.skills.summarize_chat_context_bridge._redis_url", lambda: "redis://x")
    monkeypatch.setattr("duckclaw.forge.skills.summarize_chat_context_bridge._resolve_history_session_id", lambda c: "s")
    monkeypatch.setattr("duckclaw.graphs.chat_heartbeat.is_admin_ui_chat_session", lambda c: c.startswith("admin-"))
    monkeypatch.setattr(b, "_publish_live", lambda chat, text, kind: sent.append((kind, text)))

    assert not b.auto_ack_first_tool("admin-1", "Pensando", 3, "t")          # the model thinking is not work
    assert not b.auto_ack_first_tool("tg-1", "read_sql", 3, "t")             # web chat only
    assert not b.auto_ack_first_tool("admin-1", "read_sql", None, "t")       # no turn id, no ack
    assert b.auto_ack_first_tool("admin-1", "read_sql", 3, "t")
    assert not b.auto_ack_first_tool("admin-1", "run_sandbox", 3, "t")       # once per turn
    assert b.auto_ack_first_tool("admin-1", "read_sql", 4, "t")              # next turn acks again
    assert [k for k, _ in sent] == ["reaction", "message", "reaction", "message"] and sent[0][1] == "👀"
    assert sent[1][1] in b.AUTO_ACK_PHRASES and store[b.pending_reaction_key("t", "s")] == "👀"
    assert len(store[b.pending_interim_key("t", "s")]) == 2               # stored so the history keeps them in order
