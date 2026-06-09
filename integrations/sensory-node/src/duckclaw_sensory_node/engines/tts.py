"""TTS engine — mlx-audio OmniVoice with Identity Lock (pre-approved voice tensors)."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from duckclaw_sensory_node.audio_io import audio_duration_sec, encode_ogg_opus_base64, mlx_array_to_numpy

_log = logging.getLogger("duckclaw.sensory.tts")

_DEFAULT_MODEL = "mlx-community/OmniVoice-bf16"
_TTS_TIMEOUT_MS = float((os.environ.get("DUCKCLAW_SENSORY_TTS_TIMEOUT_MS") or "2000").strip() or "2000")


@dataclass
class VoiceProfile:
    voice_id: str
    ref_text: str
    ref_tokens: Any | None = None
    ref_audio_path: Path | None = None


def _voices_dir() -> Path:
    env = (os.environ.get("DUCKCLAW_SENSORY_VOICES_DIR") or "").strip()
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[3] / "voices"


def _load_voice_profile(voice_id: str, voices_root: Path) -> VoiceProfile:
    manifest_path = voices_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"voices manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if voice_id not in manifest:
        raise KeyError(f"voice_id not in manifest: {voice_id}")
    entry = manifest[voice_id]
    if isinstance(entry, str):
        tensor_name = entry
        ref_text = ""
    elif isinstance(entry, dict):
        tensor_name = str(entry.get("file") or entry.get("tensor") or "").strip()
        ref_text = str(entry.get("ref_text") or "").strip()
    else:
        raise ValueError(f"invalid manifest entry for {voice_id}")
    tensor_path = voices_root / tensor_name
    if not tensor_path.is_file():
        raise FileNotFoundError(f"voice tensor missing: {tensor_path}")

    ref_tokens = None
    ref_audio_path = None
    suffix = tensor_path.suffix.lower()
    if suffix == ".safetensors":
        try:
            from safetensors import safe_open

            with safe_open(str(tensor_path), framework="numpy") as f:
                keys = list(f.keys())
                if "ref_tokens" in keys:
                    ref_tokens = f.get_tensor("ref_tokens")
                if "ref_text" in keys and not ref_text:
                    raw = f.get_tensor("ref_text")
                    if isinstance(raw, bytes):
                        ref_text = raw.decode("utf-8", errors="replace")
                    elif hasattr(raw, "tobytes"):
                        ref_text = raw.tobytes().decode("utf-8", errors="replace").strip("\x00")
        except Exception as exc:
            _log.warning("safetensors load failed for %s: %s", voice_id, exc)
    elif suffix in (".wav", ".ogg", ".mp3"):
        ref_audio_path = tensor_path

    return VoiceProfile(
        voice_id=voice_id,
        ref_text=ref_text,
        ref_tokens=ref_tokens,
        ref_audio_path=ref_audio_path,
    )


class TTSEngine:
    def __init__(self) -> None:
        self._model_id = (os.environ.get("DUCKCLAW_SENSORY_TTS_MODEL") or _DEFAULT_MODEL).strip()
        self._model: Any = None
        self._voices: dict[str, VoiceProfile] = {}
        self._loaded = False
        self._darwin = sys.platform == "darwin"
        self._sample_rate = 24000

    @property
    def loaded(self) -> bool:
        return self._loaded

    def warm(self) -> None:
        if not self._darwin:
            _log.warning("TTS warm skipped: not darwin")
            return
        try:
            from mlx_audio.tts.utils import load_model

            self._model = load_model(self._model_id)
            self._sample_rate = int(getattr(self._model, "sample_rate", 24000) or 24000)
            voices_root = _voices_dir()
            manifest_path = voices_root / "manifest.json"
            if manifest_path.is_file():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                for voice_id in manifest:
                    try:
                        self._voices[voice_id] = _load_voice_profile(voice_id, voices_root)
                    except Exception as exc:
                        _log.warning("voice profile load failed id=%s: %s", voice_id, exc)
            self._loaded = True
            _log.info("TTS engine ready model=%s voices=%s", self._model_id, list(self._voices))
        except ImportError as exc:
            _log.error("mlx-audio not available: %s", exc)
        except Exception as exc:
            _log.error("TTS warm failed model=%s: %s", self._model_id, exc)

    def has_voice(self, voice_id: str) -> bool:
        return voice_id in self._voices

    def synthesize(self, text: str, voice_id: str, *, speed: float = 1.0) -> dict[str, Any]:
        if not self._darwin or self._model is None:
            raise RuntimeError("TTS requires Apple Silicon with mlx-audio loaded")
        if voice_id not in self._voices:
            raise KeyError(f"voice_id not registered: {voice_id}")

        profile = self._voices[voice_id]
        t0 = time.perf_counter()
        deadline = t0 + (_TTS_TIMEOUT_MS / 1000.0)

        gen_kwargs: dict[str, Any] = {
            "text": text,
            "language": "spanish",
            "speed": speed,
            "duration_s": min(30.0, max(3.0, len(text) * 0.06)),
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
        elif profile.ref_audio_path is not None:
            gen_kwargs["ref_audio"] = str(profile.ref_audio_path)
            if profile.ref_text:
                gen_kwargs["ref_text"] = profile.ref_text

        audio_out: np.ndarray | None = None
        for result in self._model.generate(**gen_kwargs):
            if time.perf_counter() > deadline:
                raise TimeoutError("TTS inference timeout")
            audio_out = mlx_array_to_numpy(result.audio)
            break

        if audio_out is None or len(audio_out) == 0:
            raise RuntimeError("TTS produced empty audio")

        latency_ms = (time.perf_counter() - t0) * 1000.0
        if latency_ms > _TTS_TIMEOUT_MS:
            raise TimeoutError("TTS inference timeout")

        b64, _ = encode_ogg_opus_base64(audio_out, self._sample_rate)
        duration = audio_duration_sec(audio_out, self._sample_rate)
        return {
            "audio_base64": b64,
            "duration_sec": duration,
            "latency_ms": latency_ms,
        }
