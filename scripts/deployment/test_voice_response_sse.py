#!/usr/bin/env python3
"""Smoke test: playground/chat SSE with voice_response emits audio event."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path


def _load_admin_key() -> str:
    env_path = Path(os.environ.get("DUCKCLAW_ENV", "/root/duckclaw/.env"))
    if not env_path.is_file():
        raise SystemExit(f"missing env file: {env_path}")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("DUCKCLAW_ADMIN_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("DUCKCLAW_ADMIN_API_KEY not in .env")


def main() -> int:
    key = _load_admin_key()
    body = json.dumps(
        {
            "worker_id": "finanz",
            "message": "Di hola en una frase corta.",
            "chat_id": "tts-sse-smoke",
            "stream": True,
            "voice_response": True,
        }
    ).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/admin/playground/chat",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Admin-Key": key,
            "Accept": "text/event-stream",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        text = resp.read().decode("utf-8", "replace")
    has_audio = '"type": "audio"' in text or '"type":"audio"' in text
    has_done = "[DONE]" in text
    print(f"stream_len={len(text)} has_audio_event={has_audio} has_done={has_done}")
    if not has_done:
        print("FAIL: missing [DONE]", file=sys.stderr)
        return 1
    if not has_audio:
        print("FAIL: missing audio SSE event", file=sys.stderr)
        print(text[-1200:], file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
