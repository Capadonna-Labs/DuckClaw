"""Constantes y límites de entorno para síntesis NL de egress."""

from __future__ import annotations

import os

SUMMARIZE_NEW_CONTEXT_MARK = "[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]"
SUMMARIZE_STORED_CONTEXT_MARK = "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]"
SUMMARIZE_IMAGE_MARK = "[SYSTEM_DIRECTIVE: SUMMARIZE_IMAGE]"
VLM_GATEWAY_DOWN_META = "[META: VLM_GATEWAY_DOWN]"

_MAX_EVIDENCE_CHARS = 12000
_MAX_SYNTH_TOKENS = 768
_DEFAULT_ADMIN_SYNTH_MAX_TOKENS = 2048
_DEFAULT_CONTEXT_SUMMARY_SYNTH_EVIDENCE = 4500
_DEFAULT_CONTEXT_SUMMARY_SYNTH_MAX_TOKENS = 512

def _parse_bounded_int_env(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if raw.isdigit():
        return max(lo, min(hi, int(raw)))
    return default


def context_summary_synthesis_evidence_char_limit() -> int:
    """Tope de caracteres de ``<evidence>`` solo en la síntesis NL de ``rescind_*`` (SUMMARIZE_*)."""
    return _parse_bounded_int_env(
        "DUCKCLAW_CONTEXT_SUMMARY_SYNTH_MAX_CHARS",
        _DEFAULT_CONTEXT_SUMMARY_SYNTH_EVIDENCE,
        lo=1200,
        hi=_MAX_EVIDENCE_CHARS,
    )


def admin_nl_synthesis_max_output_tokens() -> int:
    """Tope de tokens de salida en síntesis NL para consola admin (respuestas largas)."""
    return _parse_bounded_int_env(
        "DUCKCLAW_ADMIN_NL_SYNTH_MAX_TOKENS",
        _DEFAULT_ADMIN_SYNTH_MAX_TOKENS,
        lo=512,
        hi=8192,
    )


def admin_reply_already_polished(text: str) -> bool:
    """
    Admin UI: si el worker ya devolvió Markdown estructurado, omitir 2.ª pasada LLM
    (evita recortes por max_tokens y duplicar trabajo).
    """
    t = (text or "").strip()
    if len(t) < 180:
        return False
    has_md = "**" in t or "##" in t
    has_list = "\n-" in t or "\n1." in t or "\n2." in t or "✅" in t or "❌" in t
    return bool(has_md and has_list)


def context_summary_synthesis_max_output_tokens() -> int:
    return _parse_bounded_int_env(
        "DUCKCLAW_CONTEXT_SUMMARY_SYNTH_MAX_TOKENS",
        _DEFAULT_CONTEXT_SUMMARY_SYNTH_MAX_TOKENS,
        lo=128,
        hi=2048,
    )


def nl_reply_synthesis_globally_disabled() -> bool:
    v = (os.environ.get("DUCKCLAW_DISABLE_NL_REPLY_SYNTHESIS") or "").strip().lower()
    return v in ("1", "true", "yes", "on")

