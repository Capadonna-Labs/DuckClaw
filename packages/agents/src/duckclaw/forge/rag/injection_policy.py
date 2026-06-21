"""When to preload PROJECT_CONTEXT / RAG blocks in playground turns."""

from __future__ import annotations

import re

_META_SKIP_RAG = re.compile(
    r"""(
        qu[eé]\s+puedes\s+hacer |
        qu[eé]\s+sabes\s+hacer |
        qu[eé]\s+documentos |
        qu[eé]\s+archivos |
        documentos?\s+disponibles |
        tienes\s+alg[uú]n\s+documento |
        formato\s+\.docx |
        listar?\s+(los\s+)?documentos |
        qu[eé]\s+hay\s+en\s+el\s+(archivo|word|docx)
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def should_inject_playground_context(user_message: str) -> bool:
    """Return False for capabilities / inventory meta turns (agent uses tools instead)."""
    raw = (user_message or "").strip()
    if not raw:
        return False
    try:
        from duckclaw.commands.fast_replies import _is_capabilities_smalltalk

        if _is_capabilities_smalltalk(raw):
            return False
    except Exception:
        pass
    if len(raw) > 320:
        return True
    return _META_SKIP_RAG.search(raw) is None
