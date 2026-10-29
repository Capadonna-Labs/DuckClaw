"""Neutralize prompt injection in tool output before the model reads it.

Every tool result (Reddit, news, Telegram, web, another worker's reply through ``invoke_worker``) is text somebody else wrote. Two
cheap defenses, applied in place so JSON results stay parseable: drop invisible characters (zero-width, bidi controls, Unicode tag
characters: the usual hiding places) and blank out the classic hijack phrases (EN/ES). It is a filter, not a guarantee; the
guarantee is the per-worker tool grants and the risk gate, which an injected sentence cannot widen.
"""

from __future__ import annotations

import re

from duckclaw.utils.logger import get_obs_logger

REDACTED = "[instrucción filtrada]"

_HIDDEN = re.compile("[​-‏‪-‮⁠-⁤﻿\U000e0000-\U000e007f]")
_INJECTION = re.compile(
    r"(?i)\b(?:ignore|disregard|forget|override|ignora|ignorar|olvida|omite)\b[^.\n]{0,40}"
    r"\b(?:previous|prior|above|earlier|all|your|system|anteriores?|previas?|todas?|tus)\b[^.\n]{0,40}"
    r"\b(?:instructions?|prompts?|rules?|guidelines|instrucciones|reglas|indicaciones)\b"
    r"|\b(?:you are now|from now on you|ahora eres|a partir de ahora (?:eres|debes))\b[^.\n]{0,60}"
    r"|\b(?:new|updated|nuevas?) (?:system )?(?:instructions?|instrucciones)\s*:"
    r"|\b(?:do not|don't|never|no|nunca) (?:tell|inform|mention|le (?:digas|avises|menciones)|avises)\b[^.\n]{0,30}\b(?:user|usuario)\b"
    r"|<\|im_(?:start|end)\|>|\[/?INST\]|</?system>",
)


def sanitize_untrusted_text(text: str, *, source: str = "") -> str:
    clean = _INJECTION.sub(REDACTED, _HIDDEN.sub("", text))
    if clean != text:
        get_obs_logger().warning("[SEC] untrusted_text filtered source=%s removed_chars=%d", source or "?", len(text) - len(clean))
    return clean
