"""Prepare worker reply text for TTS (strip admin headers, hrules)."""

from __future__ import annotations

import re

_WORKER_INSTANCE_HEADER_RE = re.compile(
    r"^[\w.-]+\s+\d+\s*[·•]\s*[^\n]*(?:\n|$)",
    re.IGNORECASE | re.MULTILINE,
)
_HRULE_RE = re.compile(r"^---+\s*$", re.MULTILINE)
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)


def prepare_text_for_tts(text: str) -> str:
    """
    TTS-safe text aligned with Sensory Node prepare_tts_text.

    Strips admin headers and emojis so Pipecat does not POST empty strings after
    sensory-node sanitization (HTTP 400 text empty after sanitization).
    """
    t = (text or "").strip()
    if not t:
        return ""
    t = _WORKER_INSTANCE_HEADER_RE.sub("", t, count=1)
    t = _HRULE_RE.sub("", t)
    t = re.sub(r"^[\w.-]+\s+\d+\s*\n", "", t, flags=re.IGNORECASE)
    t = re.sub(r"[\u200d\ufe0f]", "", t)
    t = _EMOJI_RE.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not re.search(r"\w", t, flags=re.UNICODE):
        return ""
    return t
