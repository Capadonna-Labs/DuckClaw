"""SmallWebRTC signaling routes and bot startup."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from duckclaw_pipecat.config import VoiceSettings
from duckclaw_pipecat.pipeline_factory import run_voice_pipeline
from duckclaw_pipecat.session_context import VoiceSessionContext

_log = logging.getLogger(__name__)


def register_small_webrtc_routes(app: Any, *, settings: VoiceSettings) -> None:
    """Mount /api/offer (+ ICE patch) and optional prebuilt /client UI."""
    from fastapi import Body, HTTPException
    from fastapi.responses import RedirectResponse
    from pipecat.transports.smallwebrtc.request_handler import (
        IceCandidate,
        SmallWebRTCPatchRequest,
        SmallWebRTCRequest,
        SmallWebRTCRequestHandler,
    )

    try:
        from pipecat_ai_prebuilt.frontend import PipecatPrebuiltUI

        app.mount("/client", PipecatPrebuiltUI)

        @app.get("/", include_in_schema=False)
        async def root_redirect():
            return RedirectResponse(url="/client/")
    except ImportError:
        _log.warning("pipecat prebuilt UI not installed; /client unavailable")

    handler = SmallWebRTCRequestHandler()

    def _parse_offer_body(payload: dict[str, Any]) -> SmallWebRTCRequest:
        """Parse Pipecat SDP offer from JSON request body (not query string)."""
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="JSON body required for WebRTC offer")
        if "sdp" not in payload or "type" not in payload:
            raise HTTPException(status_code=422, detail="sdp and type are required in offer body")
        return SmallWebRTCRequest.from_dict(payload)

    def _parse_patch_body(payload: dict[str, Any]) -> SmallWebRTCPatchRequest:
        """Parse ICE candidate PATCH payloads from Pipecat SmallWebRTC transport."""
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="JSON body required for ICE patch")
        pc_id = str(payload.get("pc_id") or "").strip()
        if not pc_id:
            raise HTTPException(status_code=422, detail="pc_id is required in ICE patch body")
        raw_candidates = payload.get("candidates")
        candidates: list[IceCandidate] = []
        if isinstance(raw_candidates, list):
            for item in raw_candidates:
                if not isinstance(item, dict):
                    continue
                candidates.append(
                    IceCandidate(
                        candidate=str(item.get("candidate") or ""),
                        sdp_mid=str(item.get("sdp_mid") or ""),
                        sdp_mline_index=int(item.get("sdp_mline_index") or 0),
                    )
                )
        return SmallWebRTCPatchRequest(pc_id=pc_id, candidates=candidates)

    @app.post("/api/offer")
    async def offer(payload: dict[str, Any] = Body(...)):
        request = _parse_offer_body(payload)
        req_data = request.request_data if isinstance(request.request_data, dict) else {}
        worker_id = str(req_data.get("worker_id") or settings.duckclaw_voice_default_worker).strip()
        tenant_id = str(req_data.get("tenant_id") or settings.duckclaw_voice_default_tenant).strip()
        session_id = str(req_data.get("session_id") or req_data.get("chat_id") or "").strip() or None
        actor_email = str(
            req_data.get("actor_email") or req_data.get("actor") or ""
        ).strip() or None

        session = VoiceSessionContext.create(
            default_worker=settings.duckclaw_voice_default_worker,
            default_tenant=settings.duckclaw_voice_default_tenant,
            worker_id=worker_id,
            tenant_id=tenant_id,
            session_id=session_id,
            actor_email=actor_email,
        )

        async def webrtc_connection_callback(connection: object) -> None:
            async def _run() -> None:
                try:
                    await run_voice_pipeline(connection, session=session, settings=settings)
                except Exception as exc:
                    _log.exception("voice pipeline crashed session=%s: %s", session.session_id, exc)

            asyncio.create_task(_run())

        return await handler.handle_web_request(
            request=request,
            webrtc_connection_callback=webrtc_connection_callback,
        )

    @app.patch("/api/offer")
    async def ice_candidate(payload: dict[str, Any] = Body(...)):
        request = _parse_patch_body(payload)
        await handler.handle_patch_request(request)
        return {"status": "success"}

    @app.get("/voice/session-defaults")
    async def voice_session_defaults():
        return {
            "worker_id": settings.duckclaw_voice_default_worker,
            "tenant_id": settings.duckclaw_voice_default_tenant,
            "transport": settings.duckclaw_voice_transport,
        }
