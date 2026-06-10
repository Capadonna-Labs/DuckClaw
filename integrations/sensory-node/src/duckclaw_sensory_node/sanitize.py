"""TTS text sanitization — strip markdown/emojis that confuse or break synthesis."""

from __future__ import annotations

import os
import re

_MD_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_MD_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|_(.+?)_")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_MD_STRIKE = re.compile(r"~~(.+?)~~")
_FENCED_CODE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]+)`")
_HEADER = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_HRULE = re.compile(r"^[-*_]{3,}\s*$", re.MULTILINE)
_BLOCKQUOTE = re.compile(r"^>\s?", re.MULTILINE)
_BULLET = re.compile(r"^[\t ]*[-*+]\s+", re.MULTILINE)
_NUMBERED = re.compile(r"^[\t ]*\d+\.\s+", re.MULTILINE)
_HTML = re.compile(r"<[^>]+>")
_URL = re.compile(r"https?://\S+")
_TABLE_SEP = re.compile(r"^\s*\|?[\s:\-|]+\|?\s*$")
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


def _default_max_chars() -> int:
    raw = (os.environ.get("DUCKCLAW_SENSORY_TTS_MAX_CHARS") or "1400").strip()
    try:
        return max(80, min(3000, int(raw)))
    except ValueError:
        return 1400


def _table_row_to_speech(line: str) -> str:
    if "|" not in line:
        return line
    if _TABLE_SEP.match(line):
        return " "
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    cells = [c for c in cells if c]
    if not cells:
        return " "
    return ", ".join(cells) + ". "


def sanitize_tts_text(raw: str) -> str:
    """Remove markdown, tables, emojis, and URLs before OmniVoice synthesis."""
    t = (raw or "").strip()
    if not t:
        return t

    t = _FENCED_CODE.sub(r"\1", t)
    t = _INLINE_CODE.sub(r"\1", t)
    t = _MD_IMAGE.sub(r"\1", t)
    t = _MD_LINK.sub(r"\1", t)
    t = _MD_STRIKE.sub(r"\1", t)
    t = _HEADER.sub("", t)
    t = _HRULE.sub(" ", t)
    t = _BLOCKQUOTE.sub("", t)
    t = "\n".join(_table_row_to_speech(line) for line in t.splitlines())
    t = _BULLET.sub("", t)
    t = _NUMBERED.sub("", t)
    t = _MD_BOLD.sub(lambda m: m.group(1) or m.group(2) or "", t)
    t = _MD_ITALIC.sub(lambda m: m.group(1) or m.group(2) or "", t)
    t = _HTML.sub("", t)
    t = _URL.sub("", t)
    t = _EMOJI.sub("", t)
    t = re.sub(r"\|", " ", t)
    t = re.sub(r"\n+", ". ", t)
    t = _WS.sub(" ", t).strip()
    return t


def cap_tts_text(text: str, max_chars: int) -> str:
    """Truncate at a sentence or phrase boundary for concise speech."""
    t = (text or "").strip()
    if not t or len(t) <= max_chars:
        return t
    chunk = t[:max_chars]
    for sep in (". ", "? ", "! ", "; ", ", ", " "):
        idx = chunk.rfind(sep)
        if idx >= max_chars // 3:
            return chunk[: idx + len(sep)].strip()
    return chunk.strip()


def prepare_tts_text(raw: str, *, max_chars: int | None = None) -> str:
    """Sanitize markdown and cap length for TTS."""
    cleaned = sanitize_tts_text(raw)
    if not cleaned:
        return ""
    limit = max_chars if max_chars is not None else _default_max_chars()
    return cap_tts_text(cleaned, limit)
