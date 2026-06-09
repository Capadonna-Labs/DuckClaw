"""STT engine — mlx-whisper 4-bit, in-memory only."""

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

_DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo-4bit"
_CHUNK_SEC = 30.0
_MAX_SEC = 300.0


class STTEngine:
    def __init__(self) -> None:
        self._model_repo = (os.environ.get("DUCKCLAW_SENSORY_STT_MODEL") or _DEFAULT_MODEL).strip()
        self._loaded = False
        self._darwin = sys.platform == "darwin"

    @property
    def loaded(self) -> bool:
        return self._loaded

    def warm(self) -> None:
        if not self._darwin:
            _log.warning("STT warm skipped: not darwin")
            return
        try:
            import mlx_whisper  # noqa: F401

            self._loaded = True
            _log.info("STT engine ready model=%s", self._model_repo)
        except ImportError as exc:
            _log.error("mlx-whisper not available: %s", exc)

    def transcribe(self, audio: np.ndarray, sr: int, *, language_hint: str | None = "es") -> dict[str, Any]:
        """
        Transcribe mono float32 audio. Applies 30s chunking when duration > 5 min.
        Returns {text, language_detected, processing_time_ms}.
        """
        if not self._darwin:
            raise RuntimeError("STT requires Apple Silicon (darwin)")
        import mlx_whisper

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
                result = mlx_whisper.transcribe(
                    tmp_path,
                    path_or_hf_repo=self._model_repo,
                    language=lang,
                    condition_on_previous_text=False,
                    compression_ratio_threshold=2.4,
                )
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            seg_text = (result.get("text") or "").strip()
            if seg_text:
                texts.append(seg_text)
            if result.get("language"):
                detected = str(result["language"])

        text = " ".join(texts).strip()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "text": text,
            "language_detected": detected,
            "processing_time_ms": elapsed_ms,
        }
