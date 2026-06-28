"""
HTTP bridge: STT transcript → gateway playground chat → text for Cartesia TTS.

voice_response is always false: realtime TTS is owned by Pipecat (Cartesia), not Sensory batch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from duckclaw_pipecat.text_sanitize import prepare_text_for_tts

_log = logging.getLogger(__name__)

GraphBridgeKind = Literal["worker_reply", "empty_reply", "transport_error", "gateway_rejected"]

PLAYGROUND_CHAT_PATH = "/api/v1/admin/playground/chat"

# Prepended only for Pipecat realtime voice — tells the worker that local TTS is external.
_VOICE_REALTIME_PREFIX = (
    "[Canal voz en vivo: responde en texto breve; la síntesis la realiza el pipeline "
    "local del cliente. No indiques que careces de TTS ni pidas configurar servicios cloud "
    "de voz.]\n\n"
)


@dataclass(frozen=True)
class GraphBridgeOutcome:
    kind: GraphBridgeKind
    text: str


def classify_graph_response(
    *,
    status_code: int,
    payload: dict[str, Any] | None,
    progress_phrase: str,
    empty_reply_phrase: str,
    gateway_rejected_phrase: str,
) -> GraphBridgeOutcome:
    """Classify gateway response without vertical-specific heuristics."""
    if status_code in (401, 403, 404):
        return GraphBridgeOutcome(kind="gateway_rejected", text=gateway_rejected_phrase)

    if status_code >= 500 or status_code < 200:
        return GraphBridgeOutcome(kind="transport_error", text=progress_phrase)

    data = payload if isinstance(payload, dict) else {}
    raw = str(data.get("response") or data.get("reply") or "").strip()
    if raw:
        tts_text = prepare_text_for_tts(raw)
        if tts_text:
            return GraphBridgeOutcome(kind="worker_reply", text=tts_text)
        return GraphBridgeOutcome(kind="empty_reply", text=empty_reply_phrase)
    return GraphBridgeOutcome(kind="empty_reply", text=empty_reply_phrase)


def build_playground_chat_payload(
    *,
    worker_id: str,
    tenant_id: str,
    chat_id: str,
    transcript: str,
    realtime_voice: bool = True,
) -> dict[str, Any]:
    """Build gateway playground/chat body for voice bridge invocations."""
    message_text = (transcript or "").strip()
    if realtime_voice and message_text:
        message_text = f"{_VOICE_REALTIME_PREFIX}{message_text}"
    payload: dict[str, Any] = {
        "worker_id": worker_id,
        "tenant_id": tenant_id,
        "chat_id": chat_id,
        "message": message_text,
        "stream": False,
        # Cartesia in Pipecat owns realtime TTS — not Sensory batch via gateway.
        "voice_response": False,
    }
    # Persist clean STT transcript in chat history; message keeps the voice hint for the graph.
    if realtime_voice and (transcript or "").strip():
        payload["user_incoming"] = (transcript or "").strip()
    return payload


async def invoke_playground_graph(
    *,
    gateway_url: str,
    admin_key: str,
    worker_id: str,
    tenant_id: str,
    chat_id: str,
    transcript: str,
    timeout_sec: float,
    progress_phrase: str,
    empty_reply_phrase: str,
    gateway_rejected_phrase: str = "Worker no disponible.",
    actor: str = "voice-pipecat",
    client: httpx.AsyncClient | None = None,
) -> GraphBridgeOutcome:
    """POST playground chat; never raises — returns classified outcome for TTS."""
    base = (gateway_url or "").strip().rstrip("/")
    if not base or not (admin_key or "").strip():
        _log.warning("graph bridge misconfigured: gateway_url or admin_key missing")
        return GraphBridgeOutcome(kind="transport_error", text=progress_phrase)

    url = f"{base}{PLAYGROUND_CHAT_PATH}"
    headers = {
        "X-Admin-Key": admin_key.strip(),
        "X-Duckclaw-Actor": actor,
        "Content-Type": "application/json",
    }
    body = build_playground_chat_payload(
        worker_id=worker_id,
        tenant_id=tenant_id,
        chat_id=chat_id,
        transcript=transcript,
    )

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec))
    try:
        try:
            response = await http.post(url, json=body, headers=headers)
        except httpx.TimeoutException:
            _log.warning("graph bridge timeout chat_id=%s worker=%s", chat_id, worker_id)
            return GraphBridgeOutcome(kind="transport_error", text=progress_phrase)
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            _log.warning("graph bridge network error: %s", exc)
            return GraphBridgeOutcome(kind="transport_error", text=progress_phrase)

        payload: dict[str, Any] | None = None
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                payload = parsed
        except Exception:
            payload = None

        outcome = classify_graph_response(
            status_code=response.status_code,
            payload=payload,
            progress_phrase=progress_phrase,
            empty_reply_phrase=empty_reply_phrase,
            gateway_rejected_phrase=gateway_rejected_phrase,
        )
        if outcome.kind == "transport_error":
            _log.warning(
                "graph bridge HTTP %s chat_id=%s",
                response.status_code,
                chat_id,
            )
        return outcome
    finally:
        if owns_client:
            await http.aclose()


async def invoke_playground_graph_text(
    *,
    gateway_url: str,
    admin_key: str,
    worker_id: str,
    tenant_id: str,
    chat_id: str,
    transcript: str,
    timeout_sec: float,
    progress_phrase: str,
    empty_reply_phrase: str,
    gateway_rejected_phrase: str = "Worker no disponible.",
    actor: str = "voice-pipecat",
) -> str:
    """Convenience: return TTS-ready text string."""
    outcome = await invoke_playground_graph(
        gateway_url=gateway_url,
        admin_key=admin_key,
        worker_id=worker_id,
        tenant_id=tenant_id,
        chat_id=chat_id,
        transcript=transcript,
        timeout_sec=timeout_sec,
        progress_phrase=progress_phrase,
        empty_reply_phrase=empty_reply_phrase,
        gateway_rejected_phrase=gateway_rejected_phrase,
        actor=actor,
    )
    return outcome.text
