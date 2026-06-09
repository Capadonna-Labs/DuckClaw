#!/usr/bin/env python3
"""Probe sensory STT from VPS with a minimal WAV payload."""
from __future__ import annotations

import base64
import io
import json
import sys
import urllib.error
import urllib.request
import wave

SENSORY = (sys.argv[1] if len(sys.argv) > 1 else "http://100.99.72.63:8001").rstrip("/")


def wav_b64(seconds: float = 1.0, *, tone: bool = True) -> str:
    import math
    import struct

    sr = 16000
    n = int(sr * seconds)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            if tone:
                sample = int(16000 * math.sin(2 * math.pi * 440 * i / sr))
            else:
                sample = 0
            frames.extend(struct.pack("<h", sample))
        w.writeframes(bytes(frames))
    return base64.b64encode(buf.getvalue()).decode("ascii")


def main() -> int:
    b64 = wav_b64()
    url = f"{SENSORY}/api/v1/sensory/transcribe"
    body = json.dumps({"audio_base64": b64, "language_hint": "es"}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            print("status", resp.status)
            print(resp.read().decode()[:500])
            return 0
    except urllib.error.HTTPError as exc:
        print("HTTP", exc.code, exc.read().decode()[:500])
        return 1
    except Exception as exc:
        print("ERR", type(exc).__name__, exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
