"""Environment configuration for DuckClaw-Voice PM2 service."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class VoiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    duckclaw_voice_enabled: bool = Field(default=False, alias="DUCKCLAW_VOICE_ENABLED")
    duckclaw_voice_bind_host: str = Field(default="127.0.0.1", alias="DUCKCLAW_VOICE_BIND_HOST")
    duckclaw_voice_port: int = Field(default=8012, alias="DUCKCLAW_VOICE_PORT")
    duckclaw_voice_transport: str = Field(default="small_webrtc", alias="DUCKCLAW_VOICE_TRANSPORT")

    duckclaw_voice_gateway_url: str = Field(
        default="http://127.0.0.1:8000",
        alias="DUCKCLAW_VOICE_GATEWAY_URL",
    )
    duckclaw_voice_gateway_admin_key: str = Field(default="", alias="DUCKCLAW_VOICE_GATEWAY_ADMIN_KEY")

    duckclaw_voice_default_worker: str = Field(default="default", alias="DUCKCLAW_VOICE_DEFAULT_WORKER")
    duckclaw_voice_default_tenant: str = Field(default="default", alias="DUCKCLAW_VOICE_DEFAULT_TENANT")

    duckclaw_voice_stt_provider: str = Field(default="sensory_adapter", alias="DUCKCLAW_VOICE_STT_PROVIDER")
    duckclaw_voice_tts_provider: str = Field(default="sensory_adapter", alias="DUCKCLAW_VOICE_TTS_PROVIDER")

    duckclaw_sensory_base_url: str = Field(
        default="http://127.0.0.1:8001",
        alias="DUCKCLAW_SENSORY_BASE_URL",
    )
    duckclaw_tts_default_voice_id: str = Field(
        default="default",
        alias="DUCKCLAW_TTS_DEFAULT_VOICE_ID",
    )
    duckclaw_tts_voice_map: str = Field(default="", alias="DUCKCLAW_TTS_VOICE_MAP")

    deepgram_api_key: str = Field(default="", alias="DEEPGRAM_API_KEY")
    cartesia_api_key: str = Field(default="", alias="CARTESIA_API_KEY")

    daily_api_key: str = Field(default="", alias="DAILY_API_KEY")
    daily_room_url: str = Field(default="", alias="DAILY_ROOM_URL")

    duckclaw_voice_graph_timeout_sec: float = Field(default=120.0, alias="DUCKCLAW_VOICE_GRAPH_TIMEOUT_SEC")
    duckclaw_voice_progress_phrase: str = Field(
        default="Un momento, estoy consultando datos.",
        alias="DUCKCLAW_VOICE_PROGRESS_PHRASE",
    )

    duckclaw_voice_empty_reply_phrase: str = Field(
        default="El agente no devolvió respuesta.",
        alias="DUCKCLAW_VOICE_EMPTY_REPLY_PHRASE",
    )
    duckclaw_voice_gateway_rejected_phrase: str = Field(
        default="Worker no disponible.",
        alias="DUCKCLAW_VOICE_GATEWAY_REJECTED_PHRASE",
    )
    duckclaw_voice_progress_delay_sec: float = Field(default=3.0, alias="DUCKCLAW_VOICE_PROGRESS_DELAY_SEC")

    @property
    def enabled(self) -> bool:
        raw = self.duckclaw_voice_enabled
        if isinstance(raw, str):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        return bool(raw)

    @property
    def gateway_url_normalized(self) -> str:
        return (self.duckclaw_voice_gateway_url or "").strip().rstrip("/")

    @property
    def admin_key(self) -> str:
        return (self.duckclaw_voice_gateway_admin_key or "").strip()

    @property
    def sensory_base_url_normalized(self) -> str:
        return (self.duckclaw_sensory_base_url or "").strip().rstrip("/")

    @property
    def uses_sensory_stt(self) -> bool:
        return self.duckclaw_voice_stt_provider.strip().lower() in (
            "sensory",
            "sensory_adapter",
            "mlx",
            "local",
        )

    @property
    def uses_sensory_tts(self) -> bool:
        return self.duckclaw_voice_tts_provider.strip().lower() in (
            "sensory",
            "sensory_adapter",
            "mlx",
            "local",
        )


@lru_cache(maxsize=1)
def get_settings() -> VoiceSettings:
    return VoiceSettings()
