"""
Escape de texto para Telegram Bot API con parse_mode MarkdownV2.

Los webhooks n8n → nodo Telegram suelen usar MarkdownV2; sin escapar, puntos,
paréntesis, guiones, etc. provocan 400 «can't parse entities».
"""

from __future__ import annotations

import re
from typing import Final

# Caracteres reservados en MarkdownV2 (https://core.telegram.org/bots/api#markdownv2-style)
TELEGRAM_MARKDOWN_V2_SPECIAL: Final[tuple[str, ...]] = (
    "\\",
    "_",
    "*",
    "[",
    "]",
    "(",
    ")",
    "~",
    "`",
    ">",
    "#",
    "+",
    "-",
    "=",
    "|",
    "{",
    "}",
    ".",
    "!",
)

TG_USER_MENTION_LINK_RE = re.compile(r"\[[^\]]+\]\(tg://user\?id=\d+\)")


def escape_telegram_markdown_v2(text: str) -> str:
    """Escapa el texto para envío seguro con parse_mode MarkdownV2."""
    if not text:
        return ""
    t = str(text)
    preserved: list[str] = []

    def _stash_link(m: re.Match[str]) -> str:
        preserved.append(m.group(0))
        return f"TGLINKTOKEN{len(preserved)-1}"

    t = TG_USER_MENTION_LINK_RE.sub(_stash_link, t)
    t = t.replace("\\", "\\\\")
    for c in TELEGRAM_MARKDOWN_V2_SPECIAL:
        if c == "\\":
            continue
        t = t.replace(c, "\\" + c)
    for i, raw in enumerate(preserved):
        t = t.replace(f"TGLINKTOKEN{i}", raw)
    return t
