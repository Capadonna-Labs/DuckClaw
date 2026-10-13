"""Build and run Pipecat voice pipeline for a WebRTC session."""

from __future__ import annotations

import logging
import os
import time

from duckclaw_pipecat.client_actions import CLIENT_MSG_APP_STATE, parse_app_state
from duckclaw_pipecat.config import VoiceSettings
from duckclaw_pipecat.processors.duckclaw_graph_llm import DuckClawGraphLLM
from duckclaw_pipecat.session_context import VoiceSessionContext
from duckclaw_pipecat.voice_id_resolver import resolve_sensory_voice_id
from duckclaw_pipecat.voice_runtime_state import VoiceRuntimeState

_log = logging.getLogger(__name__)

# stop_secs 0.6 cut a sentence at every natural pause and min_volume 0.4 dropped quiet
# phone speech, so STT got fragments ("¿No?", "Podemos hablar"). Env-tunable per device.
_VAD_PARAMS = dict(
    # 0.25 / 0.5 then picked up background noise as speech in a silent room: back to the
    # original volume floor, with a stricter speech-probability threshold.
    confidence=float(os.environ.get("DUCKCLAW_VOICE_VAD_CONFIDENCE", "0.7")),
    start_secs=float(os.environ.get("DUCKCLAW_VOICE_VAD_START_SECS", "0.3")),
    stop_secs=float(os.environ.get("DUCKCLAW_VOICE_VAD_STOP_SECS", "1.2")),
    min_volume=float(os.environ.get("DUCKCLAW_VOICE_VAD_MIN_VOLUME", "0.4")),
)


def warmup_voice_runtime() -> None:
    """
    Eager-load Pipecat + Silero VAD at process start.

    First WebRTC session otherwise imports cv2/av/pipecat synchronously inside
    asyncio and blocks ICE PATCH handling for tens of seconds.
    """
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADParams
    from pipecat.pipeline.pipeline import Pipeline  # noqa: F401
    from pipecat.processors.audio.vad_processor import VADProcessor  # noqa: F401

    SileroVADAnalyzer(params=VADParams(**_VAD_PARAMS))
    _log.info("voice runtime warmup complete")


def _elevenlabs_first_voice(key: str) -> str:
    """Account's first voice — same fallback the gateway uses for voice notes."""
    import json
    import urllib.request

    req = urllib.request.Request("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": key})
    with urllib.request.urlopen(req, timeout=10) as resp:
        voices = json.load(resp).get("voices") or []
    if not voices:
        raise RuntimeError("ElevenLabs: la cuenta no tiene voces; define DUCKCLAW_ELEVENLABS_VOICE_ID")
    return str(voices[0].get("voice_id") or "")


def _build_vad_processor():
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.audio.vad.vad_analyzer import VADParams
    from pipecat.processors.audio.vad_processor import VADProcessor

    return VADProcessor(
        vad_analyzer=SileroVADAnalyzer(params=VADParams(**_VAD_PARAMS)),
    )


def _register_rtvi_app_state_handler(rtvi: object, runtime: VoiceRuntimeState) -> None:
    """Persist app_state from admin UI over RTVI data channel."""

    @rtvi.event_handler("on_client_message")
    async def _on_client_message(_processor, message):  # type: ignore[no-untyped-def]
        msg_type = getattr(message, "type", "") or ""
        if msg_type != CLIENT_MSG_APP_STATE:
            return
        runtime.merge_app_state(parse_app_state(getattr(message, "data", None)))


async def run_voice_pipeline(
    webrtc_connection: object,
    *,
    session: VoiceSessionContext | None = None,
    settings: VoiceSettings | None = None,
) -> None:
    """Start STT → graph bridge → TTS for one WebRTC peer connection."""
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineParams, PipelineTask
    from pipecat.processors.frameworks.rtvi import RTVIProcessor, RTVIObserver
    from pipecat.transports.base_transport import TransportParams
    from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

    from duckclaw_pipecat.adapters.sensory_adapter import SensorySegmentedSTT, SensoryTTSService

    cfg = settings or VoiceSettings()
    ctx = session or VoiceSessionContext.create(
        default_worker=cfg.duckclaw_voice_default_worker,
        default_tenant=cfg.duckclaw_voice_default_tenant,
    )
    runtime = VoiceRuntimeState()

    def _resolve_tts_voice_id() -> str:
        return resolve_sensory_voice_id(
            worker_id=ctx.worker_id,
            app_state=runtime.app_state,
            default_voice_id=cfg.duckclaw_tts_default_voice_id,
            voice_map_json=cfg.duckclaw_tts_voice_map,
        )

    http_session = None  # owned here, closed when the call ends
    if cfg.uses_sensory_stt:
        sensory_url = cfg.sensory_base_url_normalized
        if not sensory_url:
            raise RuntimeError("DUCKCLAW_SENSORY_BASE_URL required for sensory STT")
        stt = SensorySegmentedSTT.build(base_url=sensory_url)
    elif cfg.duckclaw_voice_stt_provider.strip().lower() == "elevenlabs":
        # Scribe: far more accurate than the local model on short Spanish turns (which
        # produced 'K-O-K-O-L' / 'Instagram MQL5' from noise). Keyterms bias skill names.
        import aiohttp
        from pipecat.services.elevenlabs.stt import ElevenLabsSTTService, ElevenLabsSTTSettings
        from pipecat.transcriptions.language import Language

        key = cfg.elevenlabs_api_key.strip()
        if not key:
            raise RuntimeError("ELEVENLABS_API_KEY required when DUCKCLAW_VOICE_STT_PROVIDER=elevenlabs")
        http_session = aiohttp.ClientSession()
        # Value is quoted in .env (it has spaces); start_voice.sh passes the quotes through.
        terms = [t.strip(" \"'") for t in cfg.duckclaw_voice_stt_keyterms.split(",") if t.strip(" \"'")]
        stt = ElevenLabsSTTService(
            api_key=key,
            aiohttp_session=http_session,
            settings=ElevenLabsSTTSettings(
                model=cfg.elevenlabs_stt_model.strip() or "scribe_v1",
                language=Language.ES,
                keyterms=terms or None,
                tag_audio_events=False,  # no "[risa]" / "[música]" turned into user text
            ),
        )
    else:
        from pipecat.services.deepgram.stt import DeepgramSTTService

        if not cfg.deepgram_api_key.strip():
            raise RuntimeError("DEEPGRAM_API_KEY required when DUCKCLAW_VOICE_STT_PROVIDER=deepgram")
        stt = DeepgramSTTService(api_key=cfg.deepgram_api_key.strip())

    if cfg.uses_sensory_tts:
        sensory_url = cfg.sensory_base_url_normalized
        if not sensory_url:
            raise RuntimeError("DUCKCLAW_SENSORY_BASE_URL required for sensory TTS")
        if not _resolve_tts_voice_id().strip():
            raise RuntimeError(
                "voice_id unresolved — configure DUCKCLAW_TTS_DEFAULT_VOICE_ID "
                "and/or DUCKCLAW_TTS_VOICE_MAP to match sensory manifest"
            )
        tts = SensoryTTSService.build(
            base_url=sensory_url,
            resolve_voice_id=_resolve_tts_voice_id,
        )
    elif cfg.duckclaw_voice_tts_provider.strip().lower() == "elevenlabs":
        # HTTP, not the websocket service: with a multi-sentence reply the websocket context
        # was closed at end of turn and only the first sentence was heard.
        import aiohttp
        from pipecat.services.elevenlabs.tts import ElevenLabsHttpTTSService, ElevenLabsHttpTTSSettings

        key = cfg.elevenlabs_api_key.strip()
        if not key:
            raise RuntimeError("ELEVENLABS_API_KEY required when DUCKCLAW_VOICE_TTS_PROVIDER=elevenlabs")
        if http_session is None:
            http_session = aiohttp.ClientSession()
        tts = ElevenLabsHttpTTSService(
            api_key=key,
            aiohttp_session=http_session,
            settings=ElevenLabsHttpTTSSettings(
                voice=cfg.elevenlabs_voice_id.strip() or _elevenlabs_first_voice(key),
                model=cfg.elevenlabs_tts_model.strip() or "eleven_flash_v2_5",
            ),
        )
    else:
        from pipecat.services.cartesia.tts import CartesiaTTSService

        if not cfg.cartesia_api_key.strip():
            raise RuntimeError("CARTESIA_API_KEY required when DUCKCLAW_VOICE_TTS_PROVIDER=cartesia")
        tts = CartesiaTTSService(api_key=cfg.cartesia_api_key.strip())

    transport = SmallWebRTCTransport(
        webrtc_connection=webrtc_connection,
        params=TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    )

    vad_processor = _build_vad_processor()

    rtvi = RTVIProcessor()
    _register_rtvi_app_state_handler(rtvi, runtime)

    @rtvi.event_handler("on_client_ready")
    async def _on_client_ready(processor) -> None:  # type: ignore[no-untyped-def]
        await processor.set_bot_ready()

    graph_llm = DuckClawGraphLLM.build(session=ctx, settings=cfg, rtvi=rtvi, runtime=runtime)

    pipeline = Pipeline(
        [
            transport.input(),
            vad_processor,
            rtvi,
            stt,
            graph_llm,
            tts,
            transport.output(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=False,
            audio_in_sample_rate=16000,
            audio_out_sample_rate=24000,
        ),
        observers=[RTVIObserver(rtvi)],
    )

    _log.info(
        "voice pipeline start session=%s worker=%s tenant=%s actor=%s",
        ctx.session_id,
        ctx.worker_id,
        ctx.tenant_id,
        ctx.actor_email,
    )
    started_at = time.monotonic()
    runner = PipelineRunner()
    try:
        await runner.run(task)
    finally:
        if http_session is not None:
            await http_session.close()
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        _log.info(
            "voice pipeline end session=%s elapsed_ms=%s app_state_keys=%s",
            ctx.session_id,
            elapsed_ms,
            sorted(runtime.app_state.keys()),
        )
