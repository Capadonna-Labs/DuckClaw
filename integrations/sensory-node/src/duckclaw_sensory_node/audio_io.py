"""In-memory audio decode/encode — no disk writes for PII."""

from __future__ import annotations

import base64
import io
import struct
import wave
from typing import Any

import numpy as np

_SAMPLE_RATE_WHISPER = 16000


def decode_audio_base64(audio_b64: str) -> tuple[np.ndarray, int]:
    """
    Decode base64 audio (OGG/WAV/MP3) to mono float32 numpy array and sample rate.
    Uses soundfile; falls back to raw WAV parse for simple headers.
    """
    raw = base64.b64decode((audio_b64 or "").strip(), validate=False)
    if not raw:
        raise ValueError("empty audio payload")
    buf = io.BytesIO(raw)
    try:
        import soundfile as sf

        data, sr = sf.read(buf, dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = np.mean(data, axis=1)
        return np.asarray(data, dtype=np.float32), int(sr)
    except Exception:
        pass
    try:
        from pydub import AudioSegment

        seg = AudioSegment.from_file(io.BytesIO(raw))
        samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
        width = int(seg.sample_width)
        if width == 1:
            samples = (samples - 128.0) / 128.0
        elif width == 2:
            samples = samples / 32768.0
        elif width == 4:
            samples = samples / 2147483648.0
        else:
            denom = float(1 << (8 * width - 1))
            samples = samples / denom
        ch = int(seg.channels)
        if ch > 1:
            samples = samples.reshape(-1, ch).mean(axis=1)
        return samples.astype(np.float32), int(seg.frame_rate)
    except Exception:
        pass
    return _decode_wav_bytes(raw)


def _decode_wav_bytes(raw: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(raw), "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        frames = wf.readframes(n)
        sw = wf.getsampwidth()
        ch = wf.getnchannels()
    if sw == 2:
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        samples = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported WAV sample width: {sw}")
    if ch > 1:
        samples = samples.reshape(-1, ch).mean(axis=1)
    return samples, sr


def resample_to_16k(audio: np.ndarray, sr: int) -> np.ndarray:
    if sr == _SAMPLE_RATE_WHISPER:
        return audio
    duration = len(audio) / float(sr)
    n_out = max(1, int(round(duration * _SAMPLE_RATE_WHISPER)))
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def chunk_audio(audio: np.ndarray, sr: int, *, chunk_sec: float = 30.0, max_sec: float = 300.0) -> list[np.ndarray]:
    """Split audio into windows of chunk_sec when duration exceeds max_sec (5 min)."""
    if sr <= 0 or len(audio) == 0:
        return [audio]
    duration = len(audio) / sr
    if duration <= max_sec:
        return [audio]
    chunk_samples = int(chunk_sec * sr)
    chunks: list[np.ndarray] = []
    for start in range(0, len(audio), chunk_samples):
        chunks.append(audio[start : start + chunk_samples])
    return chunks


def encode_wav_base64(audio: np.ndarray, sr: int) -> str:
    """Encode float32 mono audio as WAV base64 (intermediate)."""
    pcm = np.clip(audio, -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())
    return base64.b64encode(buf.getvalue()).decode("ascii")


def encode_ogg_opus_base64(audio: np.ndarray, sr: int) -> tuple[str, float]:
    """
    Encode mono float audio to OGG/Opus in memory.
    Falls back to WAV if pydub/ffmpeg unavailable.
    """
    duration = len(audio) / float(sr) if sr > 0 else 0.0
    try:
        from pydub import AudioSegment

        pcm16 = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
        seg = AudioSegment(
            pcm16.tobytes(),
            frame_rate=sr,
            sample_width=2,
            channels=1,
        )
        out = io.BytesIO()
        seg.export(out, format="ogg", codec="libopus", parameters=["-ar", "48000"])
        return base64.b64encode(out.getvalue()).decode("ascii"), duration
    except Exception:
        return encode_wav_base64(audio, sr), duration


def audio_duration_sec(audio: np.ndarray, sr: int) -> float:
    return len(audio) / float(sr) if sr > 0 else 0.0


def mlx_array_to_numpy(audio: Any) -> np.ndarray:
    """Convert mlx array or numpy to float32 mono numpy."""
    if hasattr(audio, "__array__"):
        arr = np.asarray(audio, dtype=np.float32)
    else:
        try:
            import mlx.core as mx

            arr = np.array(mx.array(audio), dtype=np.float32)
        except Exception as exc:
            raise TypeError("unsupported audio tensor type") from exc
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    return arr.astype(np.float32)


def write_temp_wav_in_memory(audio: np.ndarray, sr: int) -> io.BytesIO:
    """WAV buffer for mlx-whisper transcribe (accepts file path; we use temp file pattern in engine)."""
    pcm16 = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm16.tobytes())
    buf.seek(0)
    return buf
