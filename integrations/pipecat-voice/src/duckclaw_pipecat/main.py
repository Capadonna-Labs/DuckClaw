"""Uvicorn entry: DuckClaw-Voice (Pipecat SmallWebRTC + graph bridge)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from duckclaw_pipecat.config import VoiceSettings, get_settings

_log = logging.getLogger(__name__)


def create_app(settings: VoiceSettings | None = None) -> FastAPI:
    cfg = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ARG001
        if cfg.enabled:
            try:
                from duckclaw_pipecat.pipeline_factory import warmup_voice_runtime

                await asyncio.to_thread(warmup_voice_runtime)
            except Exception as exc:
                _log.warning("voice runtime warmup failed: %s", exc)
        yield

    app = FastAPI(title="DuckClaw Voice", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        gw = cfg.gateway_url_normalized
        return {
            "ok": True,
            "enabled": cfg.enabled,
            "transport": cfg.duckclaw_voice_transport,
            "gateway_configured": bool(gw and cfg.admin_key),
            "gateway_host": gw.split("://")[-1][:80] if gw else "",
            "default_worker": cfg.duckclaw_voice_default_worker,
        }

    if not cfg.enabled:
        _log.info("DuckClaw-Voice app created in disabled mode (/health only)")
        return app

    if cfg.duckclaw_voice_transport.strip().lower() != "small_webrtc":
        _log.warning("transport %s not implemented; only small_webrtc in v1", cfg.duckclaw_voice_transport)

    try:
        from duckclaw_pipecat.transports.small_webrtc import register_small_webrtc_routes

        register_small_webrtc_routes(app, settings=cfg)
    except ImportError as exc:
        _log.error("realtime extras not installed: %s", exc)

    return app


app = create_app()
