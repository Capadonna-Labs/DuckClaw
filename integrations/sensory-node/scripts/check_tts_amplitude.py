#!/usr/bin/env python3
"""Diagnose TTS output amplitude on sensory node."""
from __future__ import annotations

import base64
import math
import struct
import sys


def peak_rms_from_wav_b64(b64: str) -> tuple[int, float, float]:
    raw = base64.b64decode(b64)
    data_off = raw.find(b"data")
    fmt_off = raw.find(b"fmt ")
    sr = struct.unpack_from("<I", raw, fmt_off + 12)[0]
    ch = struct.unpack_from("<H", raw, fmt_off + 10)[0]
    ds = struct.unpack_from("<I", raw, data_off + 4)[0]
    pcm = raw[data_off + 8 : data_off + 8 + ds]
    n = len(pcm) // 2
    samples = struct.unpack("<" + "h" * n, pcm)
    peak = max(abs(s) for s in samples) if samples else 0
    rms = math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0.0
    dur = n / max(sr, 1) / max(ch, 1)
    return peak, rms, dur


DEFAULT_VOICE_ID = "default_assistant"


def _pick_voice_id(eng) -> str:
    if eng._voices.get(DEFAULT_VOICE_ID):
        return DEFAULT_VOICE_ID
    keys = list(eng._voices.keys())
    if not keys:
        raise RuntimeError("no voice profiles loaded")
    return keys[0]


def main() -> int:
    from duckclaw_sensory_node.engines.tts import TTSEngine
    from duckclaw_sensory_node.audio_io import mlx_array_to_numpy
    import numpy as np

    eng = TTSEngine()
    eng.warm()
    print("loaded", eng.loaded, "sr", eng._sample_rate)
    print("voices", list(eng._voices.keys()))
    voice_id = _pick_voice_id(eng)
    vp = eng._voices.get(voice_id)
    if vp:
        print(
            f"{voice_id} ref_tokens",
            type(vp.ref_tokens),
            getattr(vp.ref_tokens, "shape", None),
            "ref_text_len",
            len(vp.ref_text or ""),
            "ref_audio",
            vp.ref_audio_path,
        )

    # Inspect raw model output before encode
    profile = eng._voices[voice_id]
    gen_kwargs = {
        "text": "Hola prueba uno dos tres",
        "language": "spanish",
        "speed": 1.0,
        "duration_s": 5.0,
        "num_steps": 32,
    }
    if profile.ref_tokens is not None:
        import mlx.core as mx

        ref = profile.ref_tokens
        if not isinstance(ref, mx.array):
            ref = mx.array(ref)
        gen_kwargs["ref_tokens"] = ref
        if profile.ref_text:
            gen_kwargs["ref_text"] = profile.ref_text

    audio_out = None
    for result in eng._model.generate(**gen_kwargs):
        audio_out = mlx_array_to_numpy(result.audio)
        print(
            "raw audio shape",
            audio_out.shape,
            "dtype",
            audio_out.dtype,
            "min",
            float(np.min(audio_out)),
            "max",
            float(np.max(audio_out)),
            "absmax",
            float(np.max(np.abs(audio_out))),
        )
        break

    out = eng.synthesize("Hola prueba uno dos tres", voice_id, output_format="wav")
    peak, rms, dur = peak_rms_from_wav_b64(out["audio_base64"])
    print("encoded peak", peak, "rms", round(rms, 2), "dur", round(dur, 2))
    return 0 if peak > 500 else 1


if __name__ == "__main__":
    raise SystemExit(main())
