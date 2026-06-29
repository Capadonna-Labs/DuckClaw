"""Tests for graph_bridge HTTP client and outcome classification."""

from __future__ import annotations

import httpx
import pytest
import respx

from duckclaw_pipecat.graph_bridge import (
    GraphBridgeOutcome,
    build_playground_chat_payload,
    classify_graph_response,
    invoke_playground_graph,
)

PROGRESS = "Un momento, estoy consultando datos."
EMPTY = "El agente no devolvió respuesta."
REJECTED = "Worker no disponible."


def test_build_playground_chat_payload_voice_response_false() -> None:
    body = build_playground_chat_payload(
        worker_id="default",
        tenant_id="default",
        chat_id="voice-abc",
        transcript="hola",
    )
    assert body["voice_response"] is False
    assert body["stream"] is False
    assert body["message"].endswith("hola")
    assert "Canal voz en vivo" in body["message"]
    assert body["user_incoming"] == "hola"


def test_build_playground_chat_payload_without_voice_prefix() -> None:
    body = build_playground_chat_payload(
        worker_id="default",
        tenant_id="default",
        chat_id="voice-abc",
        transcript="hola",
        realtime_voice=False,
    )
    assert body["message"] == "hola"


def test_classify_worker_reply_verbatim() -> None:
    out = classify_graph_response(
        status_code=200,
        payload={"ok": True, "response": "❌ Regla de Evidencia: no pude verificar."},
        progress_phrase=PROGRESS,
        empty_reply_phrase=EMPTY,
        gateway_rejected_phrase=REJECTED,
    )
    assert out.kind == "worker_reply"
    assert "Evidencia" in out.text
    assert out.text != PROGRESS


def test_classify_emoji_only_reply_becomes_empty() -> None:
    out = classify_graph_response(
        status_code=200,
        payload={"ok": True, "response": "🧘‍♂️ 🐯"},
        progress_phrase=PROGRESS,
        empty_reply_phrase=EMPTY,
        gateway_rejected_phrase=REJECTED,
    )
    assert out.kind == "empty_reply"
    assert out.text == EMPTY


def test_classify_empty_reply_not_progress() -> None:
    out = classify_graph_response(
        status_code=200,
        payload={"ok": True, "response": ""},
        progress_phrase=PROGRESS,
        empty_reply_phrase=EMPTY,
        gateway_rejected_phrase=REJECTED,
    )
    assert out.kind == "empty_reply"
    assert out.text == EMPTY
    assert out.text != PROGRESS


def test_classify_gateway_rejected() -> None:
    out = classify_graph_response(
        status_code=403,
        payload={"detail": "forbidden"},
        progress_phrase=PROGRESS,
        empty_reply_phrase=EMPTY,
        gateway_rejected_phrase=REJECTED,
    )
    assert out.kind == "gateway_rejected"
    assert out.text == REJECTED


def test_classify_transport_error_5xx() -> None:
    out = classify_graph_response(
        status_code=502,
        payload=None,
        progress_phrase=PROGRESS,
        empty_reply_phrase=EMPTY,
        gateway_rejected_phrase=REJECTED,
    )
    assert out.kind == "transport_error"
    assert out.text == PROGRESS


@respx.mock
@pytest.mark.asyncio
async def test_invoke_success_worker_reply() -> None:
    route = respx.post("http://gw.test/api/v1/admin/playground/chat").mock(
        return_value=httpx.Response(200, json={"ok": True, "response": "Hola desde el grafo."})
    )
    outcome = await invoke_playground_graph(
        gateway_url="http://gw.test",
        admin_key="secret",
        worker_id="default",
        tenant_id="default",
        chat_id="voice-1",
        transcript="hola",
        timeout_sec=30.0,
        progress_phrase=PROGRESS,
        empty_reply_phrase=EMPTY,
        gateway_rejected_phrase=REJECTED,
    )
    assert route.called
    req = route.calls[0].request
    assert req.headers["X-Admin-Key"] == "secret"
    assert req.headers["X-Duckclaw-Actor"] == "voice-pipecat"
    assert outcome.kind == "worker_reply"
    assert "grafo" in outcome.text


@respx.mock
@pytest.mark.asyncio
async def test_invoke_timeout_transport_error() -> None:
    respx.post("http://gw.test/api/v1/admin/playground/chat").mock(
        side_effect=httpx.TimeoutException("slow")
    )
    outcome = await invoke_playground_graph(
        gateway_url="http://gw.test",
        admin_key="secret",
        worker_id="default",
        tenant_id="default",
        chat_id="voice-1",
        transcript="hola",
        timeout_sec=1.0,
        progress_phrase=PROGRESS,
        empty_reply_phrase=EMPTY,
    )
    assert outcome.kind == "transport_error"
    assert outcome.text == PROGRESS


@respx.mock
@pytest.mark.asyncio
async def test_invoke_200_empty_not_progress() -> None:
    respx.post("http://gw.test/api/v1/admin/playground/chat").mock(
        return_value=httpx.Response(200, json={"ok": True, "response": ""})
    )
    outcome = await invoke_playground_graph(
        gateway_url="http://gw.test",
        admin_key="secret",
        worker_id="default",
        tenant_id="default",
        chat_id="voice-1",
        transcript="hola",
        timeout_sec=30.0,
        progress_phrase=PROGRESS,
        empty_reply_phrase=EMPTY,
    )
    assert outcome.kind == "empty_reply"
    assert outcome.text == EMPTY
