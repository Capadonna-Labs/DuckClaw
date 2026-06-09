"""TTS text sanitization — strip markdown/emojis that cause acoustic hallucinations."""

from __future__ import annotations

import re

_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|_(.+?)_")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_URL = re.compile(r"https?://\S+")
_EMOJI = re.compile(
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
_WS = re.compile(r"\s+")


def sanitize_tts_text(raw: str) -> str:
    """Remove markdown, emojis, and URLs before OmniVoice synthesis."""
    t = (raw or "").strip()
    if not t:
        return t
    t = _MD_LINK.sub(r"\1", t)
    t = _MD_BOLD.sub(r"\1", t)
    t = _MD_ITALIC.sub(lambda m: m.group(1) or m.group(2) or "", t)
    t = _URL.sub("", t)
    t = _EMOJI.sub("", t)
    t = _WS.sub(" ", t).strip()
    return t
