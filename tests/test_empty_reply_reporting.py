"""Empty-reply reporting: never leave admin/Telegram with a blank bubble."""

from __future__ import annotations

from pathlib import Path


def test_chat_sse_imports_sse_done() -> None:
    text = Path("services/api-gateway/core/chat_sse.py").read_text(encoding="utf-8")
    assert "sse_done" in text
    assert "empty reply substituted" in text
    assert "La conexión SSE se cerró" in text


def test_finalize_substitutes_empty_reply() -> None:
    text = Path("services/api-gateway/core/chat_invoke_finalize.py").read_text(encoding="utf-8")
    assert "finalize empty reply substituted" in text
    assert "No hubo respuesta del agente en este turno" in text


def test_admin_ui_no_longer_uses_sin_respuesta_stub() -> None:
    turn = Path("apps/duckclaw-admin/src/components/chat/runAdminChatTurn.ts").read_text(
        encoding="utf-8"
    )
    assert "(sin respuesta)" not in turn
    assert "No hubo respuesta del agente" in turn


def test_manager_wall_clock_timeout_does_not_replan() -> None:
    text = Path("packages/agents/src/duckclaw/manager/manager_nodes_invoke.py").read_text(
        encoding="utf-8"
    )
    assert "_wall_clock_timeout" in text
    assert "reporting to user (no replan)" in text
    assert "_manager_worker_timeout_sec" in text


def test_invoke_timeout_uses_graph_interrupt_marker() -> None:
    text = Path("packages/agents/src/duckclaw/workers/worker_invoke.py").read_text(
        encoding="utf-8"
    )
    body = text.split("def invoke_worker_graph")[1].split("def extract_worker_invoke_reply")[0]
    assert "request_graph_interrupt" in body
    assert "request_chat_cancel(cid)" not in body
