import base64
import io
import wave

import numpy as np

from duckclaw_sensory_node.audio_io import chunk_audio, decode_audio_base64, resample_to_16k


def _wav_b64(samples: np.ndarray, sr: int = 16000) -> str:
    pcm = (samples * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_decode_wav_roundtrip():
    samples = np.zeros(1600, dtype=np.float32)
    audio, sr = decode_audio_base64(_wav_b64(samples))
    assert sr == 16000
    assert len(audio) == 1600


def test_chunk_audio_long():
    sr = 16000
    six_min = np.zeros(sr * 360, dtype=np.float32)
    chunks = chunk_audio(six_min, sr, chunk_sec=30.0, max_sec=300.0)
    assert len(chunks) == 12


def test_resample_to_16k_noop():
    a = np.ones(100, dtype=np.float32)
    out = resample_to_16k(a, 16000)
    assert len(out) == 100
