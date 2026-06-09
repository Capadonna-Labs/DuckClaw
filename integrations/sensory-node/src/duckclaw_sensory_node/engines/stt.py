"""STT engine — mlx-audio Whisper on Apple Silicon, in-memory only."""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
from typing import Any

import numpy as np

from duckclaw_sensory_node.audio_io import chunk_audio, resample_to_16k, write_temp_wav_in_memory

_log = logging.getLogger("duckclaw.sensory.stt")

# mlx_whisper cannot load mlx-audio-plus converted weights; use mlx_audio.stt instead.
_DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo-asr-fp16"
_CHUNK_SEC = 30.0
_MAX_SEC = 300.0


def _text_from_stt_output(result: Any) -> str:
    text = getattr(result, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    segments = getattr(result, "segments", None) or []
    parts: list[str] = []
    for seg in segments:
        if isinstance(seg, dict):
            part = (seg.get("text") or "").strip()
        else:
            part = (getattr(seg, "text", None) or "").strip()
        if part:
            parts.append(part)
    return " ".join(parts).strip()


class STTEngine:
    def __init__(self) -> None:
        self._model_repo = (os.environ.get("DUCKCLAW_SENSORY_STT_MODEL") or _DEFAULT_MODEL).strip()
        self._loaded = False
        self._darwin = sys.platform == "darwin"
        self._model: Any = None

    @property
    def loaded(self) -> bool:
        return self._loaded

    def warm(self) -> None:
        if not self._darwin:
            _log.warning("STT warm skipped: not darwin")
            return
        try:
            from mlx_audio.stt.utils import load_model

            self._model = load_model(self._model_repo)
            self._loaded = True
            _log.info("STT engine ready model=%s", self._model_repo)
        except Exception as exc:
            _log.error("STT warm failed model=%s: %s", self._model_repo, exc)

    def transcribe(self, audio: np.ndarray, sr: int, *, language_hint: str | None = "es") -> dict[str, Any]:
        """
        Transcribe mono float32 audio. Applies 30s chunking when duration > 5 min.
        Returns {text, language_detected, processing_time_ms}.
        """
        if not self._darwin:
            raise RuntimeError("STT requires Apple Silicon (darwin)")
        if not self._loaded or self._model is None:
            raise RuntimeError("STT model not loaded")

        from mlx_audio.stt.generate import generate_transcription

        t0 = time.perf_counter()
        audio_16k = resample_to_16k(audio, sr)
        chunks = chunk_audio(audio_16k, 16000, chunk_sec=_CHUNK_SEC, max_sec=_MAX_SEC)
        lang = (language_hint or "es").strip() or "es"
        texts: list[str] = []
        detected = lang

        for chunk in chunks:
            buf = write_temp_wav_in_memory(chunk, 16000)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(buf.read())
                tmp_path = tmp.name
            try:
                result = generate_transcription(
                    model=self._model,
                    audio=tmp_path,
                    verbose=False,
                    language=lang,
                )
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            seg_text = _text_from_stt_output(result)
            if seg_text:
                texts.append(seg_text)
            out_lang = getattr(result, "language", None)
            if out_lang:
                detected = str(out_lang)

        text = " ".join(texts).strip()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "text": text,
            "language_detected": detected,
            "processing_time_ms": elapsed_ms,
        }
