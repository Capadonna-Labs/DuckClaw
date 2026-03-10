"""Pipeline multimodal: voz (Whisper) y visión (VLM) locales."""

from duckclaw.multimodal.transcriber import transcribe_audio
from duckclaw.multimodal.vision import describe_image

__all__ = ["transcribe_audio", "describe_image"]
