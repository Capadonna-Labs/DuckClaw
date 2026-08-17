"""SSE admin heartbeats y mensajes de error amigables."""
from __future__ import annotations

import sys
from pathlib import Path

_gw = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))

from core.sse_stream import friendly_chat_error_message, sse_heartbeat  # noqa: E402


def test_sse_heartbeat_payload() -> None:
    raw = sse_heartbeat("Paso actual", kind="tool")
    assert '"type": "heartbeat"' in raw
    assert "Paso actual" in raw
    assert '"kind": "tool"' in raw


def test_sse_heartbeat_worker_and_slot() -> None:
    raw = sse_heartbeat("Paso actual", kind="status", worker_id="BI-Analyst", swarm_slot=2)
    assert '"worker_id": "BI-Analyst"' in raw
    assert '"swarm_slot": 2' in raw


def test_parse_admin_heartbeat_payload_worker_fields() -> None:
    from core.admin_chat_heartbeat import parse_admin_heartbeat_payload

    parsed = parse_admin_heartbeat_payload(
        '{"text":"ok","kind":"tool","worker_id":"BI-Analyst","swarm_slot":3}'
    )
    assert parsed is not None
    assert parsed["worker_id"] == "BI-Analyst"
    assert parsed["swarm_slot"] == 3


def test_parse_admin_heartbeat_payload_tool_fields() -> None:
    from core.admin_chat_heartbeat import parse_admin_heartbeat_payload

    parsed = parse_admin_heartbeat_payload(
        '{"text":"🔄 Usando: read_sql","kind":"tool","tool_name":"read_sql",'
        '"tool_phase":"done","elapsed_ms":12.3}'
    )
    assert parsed is not None
    assert parsed["tool_name"] == "read_sql"
    assert parsed["tool_phase"] == "done"
    assert parsed["elapsed_ms"] == 12.3


def test_iter_admin_heartbeats_with_lite_store() -> None:
    """Desktop lite: heartbeats must flow without Redis."""
    import asyncio
    import json

    from core.admin_chat_heartbeat import admin_heartbeat_channel, iter_admin_heartbeats
    from duckclaw.lite_session_store import LiteSessionStore

    store = LiteSessionStore()
    chat_id = "admin-conv-lite-hb"
    channel = admin_heartbeat_channel(chat_id)
    stop = asyncio.Event()

    async def _run() -> None:
        received: list[dict] = []

        async def _listen() -> None:
            async for item in iter_admin_heartbeats(store, chat_id, stop=stop):
                received.append(item)
                stop.set()
                break

        listener = asyncio.create_task(_listen())
        await asyncio.sleep(0.05)
        payload = json.dumps(
            {
                "text": "🔄 Usando: inspect_schema",
                "kind": "tool",
                "tool_name": "inspect_schema",
                "tool_phase": "start",
            },
            ensure_ascii=False,
        )
        assert store.publish(channel, payload) == 1
        await asyncio.wait_for(listener, timeout=2.0)
        assert len(received) == 1
        assert received[0]["tool_name"] == "inspect_schema"
        assert received[0]["kind"] == "tool"

    asyncio.run(_run())


def test_sse_heartbeat_tool_fields() -> None:
    raw = sse_heartbeat(
        "🔄 Usando: read_sql",
        kind="tool",
        tool_name="read_sql",
        tool_phase="start",
    )
    assert '"tool_name": "read_sql"' in raw
    assert '"tool_phase": "start"' in raw


def test_friendly_chat_error_mlx_port() -> None:
    msg = friendly_chat_error_message(
        ConnectionError("[Errno 61] Connection refused connecting to http://127.0.0.1:8080/v1")
    )
    assert "8080" in msg
    assert "motor local" in msg
