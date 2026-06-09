#!/usr/bin/env python3
import os
import traceback

os.environ.setdefault("DUCKCLAW_SENSORY_TTS_TIMEOUT_MS", "45000")

from duckclaw_sensory_node.engines.tts import TTSEngine

e = TTSEngine()
e.warm()
print("loaded", e.loaded, "voices", list(e._voices.keys()))
for vid, p in e._voices.items():
    print(vid, "ref_tokens", p.ref_tokens is not None, "shape", getattr(p.ref_tokens, "shape", None))
try:
    r = e.synthesize("Hola prueba corta", "leila_assistant")
    print("ok audio_len", len(r.get("audio_base64", "")))
except Exception:
    traceback.print_exc()
