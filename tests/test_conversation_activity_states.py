"""Conversation list traffic light: working / awaiting approval / idle, read from Redis only."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_gw = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))


class _Redis:
    def __init__(self, data: dict[str, str]) -> None:
        self.data = data

    async def mget(self, keys):
        return [self.data.get(k) for k in keys]


def test_activity_states_per_conversation() -> None:
    from routers.admin_domains.playground.conversations_routes import _activity_states

    redis = _Redis({
        "duckclaw:activity:a": json.dumps({"status": "BUSY", "task": "/datos_alternativos", "started_at": 1}),
        "duckclaw:activity:b": None,
        "duckclaw:mcp_pending_chat:b": "act-1",
    })
    out = asyncio.run(_activity_states(redis, ["a", "b", "c"]))
    assert out["a"] == {"activity": "working", "activity_task": "/datos_alternativos", "activity_since": 1}
    assert out["b"] == {"activity": "awaiting_approval"}
    assert out["c"] == {"activity": "idle"}
    assert asyncio.run(_activity_states(None, ["a"])) == {}
