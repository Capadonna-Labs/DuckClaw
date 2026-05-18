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
    raw = sse_heartbeat("Paso actual", kind="status", worker_id="finanz", swarm_slot=2)
    assert '"worker_id": "finanz"' in raw
    assert '"swarm_slot": 2' in raw


def test_parse_admin_heartbeat_payload_worker_fields() -> None:
    from core.admin_chat_heartbeat import parse_admin_heartbeat_payload

    parsed = parse_admin_heartbeat_payload(
        '{"text":"ok","kind":"tool","worker_id":"Quant-Trader","swarm_slot":3}'
    )
    assert parsed is not None
    assert parsed["worker_id"] == "Quant-Trader"
    assert parsed["swarm_slot"] == 3


def test_friendly_chat_error_mlx_port() -> None:
    msg = friendly_chat_error_message(
        ConnectionError("[Errno 61] Connection refused connecting to http://127.0.0.1:8080/v1")
    )
    assert "8080" in msg
    assert "MLX" in msg
