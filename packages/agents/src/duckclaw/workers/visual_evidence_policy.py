"""Worker-local policy helpers for visual-evidence graph retries."""

from __future__ import annotations

import os


def visual_evidence_max_retries() -> int:
    """Return the non-negative retry cap for visual-evidence repair turns."""
    raw = (os.environ.get("DUCKCLAW_VISUAL_EVIDENCE_MAX_RETRIES") or "1").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 1
    return max(0, n)


__all__ = ["visual_evidence_max_retries"]
