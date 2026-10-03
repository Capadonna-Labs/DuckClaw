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


def test_sse_heartbeat_tool_rename_only_on_done() -> None:
    # Model row: running "Pensando" relabeled to "Escribiendo respuesta" on done.
    done = sse_heartbeat(
        "🧠 Pensando", kind="tool", tool_name="Pensando", tool_phase="done",
        elapsed_ms=900, tool_rename="Escribiendo respuesta",
    )
    assert '"tool_rename": "Escribiendo respuesta"' in done
    start = sse_heartbeat(
        "🧠 Pensando", kind="tool", tool_name="Pensando", tool_phase="start",
        tool_rename="Escribiendo respuesta",
    )
    assert "tool_rename" not in start


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


def test_admin_heartbeat_turn_user_index_roundtrip() -> None:
    from core.admin_chat_heartbeat import parse_admin_heartbeat_payload

    parsed = parse_admin_heartbeat_payload(
        '{"text":"read_sql","kind":"tool","tool_name":"read_sql","turn_user_index":7}'
    )
    assert parsed is not None
    assert parsed["turn_user_index"] == 7

    raw = sse_heartbeat("read_sql", kind="tool", turn_user_index=7)
    assert '"turn_user_index": 7' in raw


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


def test_reset_admin_heartbeat_backlog_clears_previous_turn() -> None:
    import asyncio

    from core.admin_chat_heartbeat import (
        admin_heartbeat_backlog_key,
        list_admin_heartbeat_backlog,
        reset_admin_heartbeat_backlog,
    )

    class FakeRedis:
        def __init__(self) -> None:
            self.lists = {admin_heartbeat_backlog_key("c1"): ['{"text": "old", "kind": "tool", "tool_name": "read_sql"}']}

        async def delete(self, key: str) -> None:
            self.lists.pop(key, None)

        async def lrange(self, key: str, start: int, end: int) -> list[str]:
            return list(self.lists.get(key, []))

    r = FakeRedis()
    assert asyncio.run(list_admin_heartbeat_backlog(r, "c1"))  # previous turn's event
    asyncio.run(reset_admin_heartbeat_backlog(r, "c1"))
    assert asyncio.run(list_admin_heartbeat_backlog(r, "c1")) == []


def test_parse_admin_heartbeat_payload_keeps_event_ts() -> None:
    # ts identifies each event for the detached (polling) UI; repeats must stay distinct.
    import json

    from core.admin_chat_heartbeat import parse_admin_heartbeat_payload

    a = parse_admin_heartbeat_payload(json.dumps({"text": "🧠 Pensando", "kind": "tool", "tool_name": "Pensando", "tool_phase": "start", "ts": 1000.5}))
    b = parse_admin_heartbeat_payload(json.dumps({"text": "🧠 Pensando", "kind": "tool", "tool_name": "Pensando", "tool_phase": "start", "ts": 2000.25}))
    assert a["ts"] == 1000.5 and b["ts"] == 2000.25


def test_sandbox_artifacts_survive_backlog_and_sse() -> None:
    """Charts from run_sandbox render inline only if artifact ids reach the UI (SSE and iOS poll)."""
    import json

    from core.admin_chat_heartbeat import parse_admin_heartbeat_payload

    raw = json.dumps({"text": "Sandbox: 2 artefactos", "kind": "visual", "artifact_ids": ["a1", "a2"], "sandbox_run_id": "r9"})
    parsed = parse_admin_heartbeat_payload(raw)
    assert parsed["artifact_ids"] == ["a1", "a2"] and parsed["sandbox_run_id"] == "r9"
    sse = sse_heartbeat("Sandbox: 2 artefactos", kind="visual", artifact_ids=["a1"], sandbox_run_id="r9")
    assert '"artifact_ids": ["a1"]' in sse and '"sandbox_run_id": "r9"' in sse


def test_startup_closes_turns_killed_by_restart() -> None:
    """A restart kills in-flight turns; detached clients wait for turn_done, so startup must emit it."""
    import asyncio
    import json

    from core.admin_chat_heartbeat import admin_heartbeat_backlog_key, close_orphaned_admin_turns

    running = admin_heartbeat_backlog_key("c-running")
    done = admin_heartbeat_backlog_key("c-done")

    class FakeRedis:
        def __init__(self) -> None:
            self.lists = {
                running: ['{"text": "🔄 Usando: x", "kind": "tool", "tool_name": "x", "tool_phase": "start"}'],
                done: ['{"text": "turn done", "kind": "turn_done"}'],
            }

        async def scan_iter(self, match: str):
            for k in list(self.lists):
                yield k

        async def lrange(self, key: str, start: int, end: int) -> list[str]:
            return self.lists[key][start:] if start < 0 else self.lists[key]

        async def rpush(self, key: str, value: str) -> None:
            self.lists[key].append(value)

    r = FakeRedis()
    assert asyncio.run(close_orphaned_admin_turns(r)) == 1
    assert json.loads(r.lists[running][-1])["kind"] == "turn_done"
    assert len(r.lists[done]) == 1


def test_last_turn_tokens_roundtrip() -> None:
    """Context-window header data survives reloads/detached turns via Redis."""
    import asyncio

    from core.admin_chat_heartbeat import load_admin_turn_tokens, save_admin_turn_tokens

    class FakeRedis:
        def __init__(self) -> None:
            self.kv: dict = {}

        async def set(self, key, value, ex=None):  # noqa: ANN001
            self.kv[key] = value

        async def get(self, key):  # noqa: ANN001
            return self.kv.get(key)

    r = FakeRedis()
    asyncio.run(save_admin_turn_tokens(r, "c1", {"response": "hola"}))  # fly ack: nothing saved
    assert asyncio.run(load_admin_turn_tokens(r, "c1")) is None
    asyncio.run(save_admin_turn_tokens(r, "c1", {"usage_tokens": {"input_tokens": 900}, "context_estimated_tokens": 1200}))
    assert asyncio.run(load_admin_turn_tokens(r, "c1")) == {
        "usage_tokens": {"input_tokens": 900},
        "context_estimated_tokens": 1200,
    }
