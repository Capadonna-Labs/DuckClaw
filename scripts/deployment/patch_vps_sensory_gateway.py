#!/usr/bin/env python3
"""One-shot patch: sensory proxy on VPS gateway (run on VPS)."""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path("/root/duckclaw")
ENV = REPO / ".env"
MAIN = REPO / "services/api-gateway/main.py"
ADMIN = REPO / "services/api-gateway/routers/admin.py"

VOICE_BLOCK = r'''
class PlaygroundVoiceBody(BaseModel):
    """Nota de voz → STT → agente → TTS (sin Telegram). STT/TTS son batch; texto del agente puede usar SSE en /playground/chat."""

    worker_id: str = Field(default="default", max_length=64)
    chat_id: str = Field(default="admin-playground", max_length=128)
    tenant_id: str = Field(default="default", max_length=64)
    project_id: str | None = Field(default=None, max_length=64)
    audio_base64: str = Field(..., min_length=8, description="OGG/WAV/WebM base64 desde el navegador")
    language_hint: str | None = Field(default="es", max_length=16)
    voice_response: bool = Field(
        default=True,
        description="Si true, sintetiza respuesta con TTS (Identity Lock). Si falla, solo texto.",
    )


'''

VOICE_ROUTE = Path(__file__).resolve().parent.parent.parent / "services/api-gateway/routers/_vps_voice_route_snippet.py"


def patch_env() -> None:
    text = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    line = "DUCKCLAW_SENSORY_BASE_URL=http://100.99.72.63:8001"
    if "DUCKCLAW_SENSORY_BASE_URL" in text:
        text = re.sub(r"^DUCKCLAW_SENSORY_BASE_URL=.*$", line, text, flags=re.M)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += f"\n# Sensory node (Mac mini via Tailscale)\n{line}\n"
    ENV.write_text(text, encoding="utf-8")
    print("patched .env")


def patch_main() -> None:
    text = MAIN.read_text(encoding="utf-8")
    marker = "try:\n    from duckclaw.graphs.novnc_routes import build_novnc_router"
    block = """try:
    from routers.sensory import router as sensory_router
    app.include_router(sensory_router)
except ImportError as _sensory_imp_err:
    _gateway_log.warning("Sensory router omitido: %s", _sensory_imp_err)

"""
    if "routers.sensory" in text:
        print("main.py already has sensory router")
        return
    if marker not in text:
        raise SystemExit("main.py marker not found")
    text = text.replace(marker, block + marker, 1)
    MAIN.write_text(text, encoding="utf-8")
    print("patched main.py")


def patch_admin() -> None:
    text = ADMIN.read_text(encoding="utf-8")
    if "playground/voice" in text:
        print("admin.py already has playground/voice")
        return
    anchor = "class PlaygroundChatCancelBody(BaseModel):"
    if anchor not in text:
        raise SystemExit("admin.py anchor not found")

    # Load route from local repo if snippet file exists; else inline minimal from sensory deploy
    route_path = REPO / "services/api-gateway/routers/_playground_voice_route.py"
    if not route_path.exists():
        raise SystemExit(f"missing {route_path} — scp _playground_voice_route.py first")

    route = route_path.read_text(encoding="utf-8")
    insert = VOICE_BLOCK + route + "\n\n"
    text = text.replace(anchor, insert + anchor, 1)
    ADMIN.write_text(text, encoding="utf-8")
    print("patched admin.py")


def main() -> None:
    patch_env()
    patch_main()
    patch_admin()


if __name__ == "__main__":
    main()
