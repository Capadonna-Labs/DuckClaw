"""Pipecat processor: STT transcript → DuckClaw gateway graph → LLM text for TTS."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from duckclaw_pipecat.client_actions import build_update_state
from duckclaw_pipecat.config import VoiceSettings
from duckclaw_pipecat.graph_bridge import invoke_playground_graph
from duckclaw_pipecat.processors.progress_tts import invoke_graph_with_progress
from duckclaw_pipecat.session_context import VoiceSessionContext
from duckclaw_pipecat.voice_runtime_state import VoiceRuntimeState

if TYPE_CHECKING:
    from pipecat.processors.frame_processor import FrameDirection

_log = logging.getLogger(__name__)


def _require_pipecat():
    from pipecat.frames.frames import (
        InterimTranscriptionFrame,
        LLMFullResponseEndFrame,
        LLMFullResponseStartFrame,
        LLMTextFrame,
        TranscriptionFrame,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

    return (
        FrameProcessor,
        FrameDirection,
        TranscriptionFrame,
        InterimTranscriptionFrame,
        LLMTextFrame,
        LLMFullResponseStartFrame,
        LLMFullResponseEndFrame,
    )


class DuckClawGraphLLM:
    """Factory for the Pipecat FrameProcessor (lazy import pipecat)."""

    @staticmethod
    def build(
        *,
        session: VoiceSessionContext,
        settings: VoiceSettings,
        rtvi: object | None = None,
        runtime: VoiceRuntimeState | None = None,
    ):
        (
            FrameProcessor,
            FrameDirection,
            TranscriptionFrame,
            InterimTranscriptionFrame,
            LLMTextFrame,
            LLMFullResponseStartFrame,
            LLMFullResponseEndFrame,
        ) = _require_pipecat()

        class _Processor(FrameProcessor):
            def __init__(self) -> None:
                super().__init__()

            async def process_frame(self, frame, direction):  # type: ignore[no-untyped-def]
                await super().process_frame(frame, direction)

                if isinstance(frame, InterimTranscriptionFrame):
                    await self.push_frame(frame, direction)
                    return

                if not isinstance(frame, TranscriptionFrame):
                    await self.push_frame(frame, direction)
                    return

                text = (frame.text or "").strip()
                if not text:
                    return
                if hasattr(frame, "finalized") and not frame.finalized:
                    return

                async def _emit_graph_phase(phase: str, elapsed_ms: int = 0) -> None:
                    if rtvi is None:
                        return
                    send = getattr(rtvi, "send_server_message", None)
                    if not callable(send):
                        return
                    await send(
                        build_update_state(
                            phase=phase,  # type: ignore[arg-type]
                            worker_id=session.worker_id,
                            elapsed_ms=elapsed_ms,
                        )
                    )

                async def _emit_tts_text(text_to_speak: str) -> None:
                    """Wrap reply in LLM turn frames so Pipecat TTS lifecycle stays coherent."""
                    await self.push_frame(LLMFullResponseStartFrame())
                    await self.push_frame(LLMTextFrame(text_to_speak))
                    await self.push_frame(LLMFullResponseEndFrame())

                async def _on_progress(phrase: str) -> None:
                    await _emit_tts_text(phrase)

                async def _invoke():
                    return await invoke_playground_graph(
                        gateway_url=settings.gateway_url_normalized,
                        admin_key=settings.admin_key,
                        worker_id=session.worker_id,
                        tenant_id=session.tenant_id,
                        chat_id=session.chat_id,
                        transcript=text,
                        timeout_sec=settings.duckclaw_voice_graph_timeout_sec,
                        progress_phrase=settings.duckclaw_voice_progress_phrase,
                        empty_reply_phrase=settings.duckclaw_voice_empty_reply_phrase,
                        gateway_rejected_phrase=settings.duckclaw_voice_gateway_rejected_phrase,
                        actor=session.actor_email,
                    )

                try:
                    await _emit_graph_phase("graph_invoke")
                    outcome = await invoke_graph_with_progress(
                        _invoke,
                        progress_phrase=settings.duckclaw_voice_progress_phrase,
                        delay_sec=settings.duckclaw_voice_progress_delay_sec,
                        on_progress=_on_progress,
                    )
                    await _emit_graph_phase("idle")
                    if outcome.text:
                        await _emit_tts_text(outcome.text)
                except Exception as exc:
                    _log.exception("duckclaw graph llm failed: %s", exc)
                    await _emit_graph_phase("idle")
                    await _emit_tts_text("No pude procesar tu mensaje en este momento.")

        return _Processor()
