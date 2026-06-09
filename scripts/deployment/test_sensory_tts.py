#!/usr/bin/env python3
import json
import sys
import urllib.request

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/api/v1/sensory/synthesize"
payload = json.dumps({"text": "Hola prueba", "voice_id": "leila_assistant"}).encode()
req = urllib.request.Request(
    url,
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        body = json.loads(r.read())
        print("status", r.status, "audio_len", len(body.get("audio_base64") or ""), "latency_ms", body.get("latency_ms"))
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode()[:500])
