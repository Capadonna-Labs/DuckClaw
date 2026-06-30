#!/usr/bin/env python3
"""Smoke test TTS duration on sensory node (run on VPS)."""
from __future__ import annotations

import json
import os
import sys
import urllib.request

BASE = (os.environ.get("SENSORY_URL") or "http://100.99.72.63:8001").rstrip("/")
text = ("Frase larga de prueba post reinicio. " * 80)[:1400]
payload = json.dumps(
    {"text": text, "voice_id": "default_assistant", "output_format": "wav"}
).encode()
req = urllib.request.Request(
    f"{BASE}/api/v1/sensory/synthesize",
    data=payload,
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=120) as r:
    d = json.loads(r.read())
print(
    f"input_chars={len(text)} duration_sec={d.get('duration_sec'):.2f} "
    f"latency_ms={d.get('latency_ms'):.0f}"
)
