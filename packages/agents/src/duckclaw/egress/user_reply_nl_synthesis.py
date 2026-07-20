"""
Síntesis LLM de la respuesta visible al usuario (Telegram): evita JSON/SQL/código crudo.

Spec: docs/architecture/GATEWAY_PROCESS_BOUNDARIES.md
Fachada: owners en ``user_reply_nl_*`` del mismo paquete.
"""

from __future__ import annotations

from duckclaw.egress.user_reply_nl_config import (
    SUMMARIZE_IMAGE_MARK,
    SUMMARIZE_NEW_CONTEXT_MARK,
    SUMMARIZE_STORED_CONTEXT_MARK,
    VLM_GATEWAY_DOWN_META,
    admin_nl_synthesis_max_output_tokens,
    admin_reply_already_polished,
    context_summary_synthesis_evidence_char_limit,
    context_summary_synthesis_max_output_tokens,
    nl_reply_synthesis_globally_disabled,
)
from duckclaw.egress.user_reply_nl_context_summary import (
    context_summary_synthesis_acceptable,
    context_summary_synthesis_has_useful_bullets,
    incoming_has_context_summarize_directive,
    repair_summarize_new_context_egress,
    replace_bare_summarize_image_on_vlm_gateway_down,
    replace_bare_wrong_summarize_stored_echo,
    reply_is_trivial_for_context_summary,
    rescind_trivial_context_summary_reply,
    state_evidence_for_context_summary_rescind,
    telegram_stored_context_summary_body_when_model_trivial,
)
from duckclaw.egress.user_reply_nl_synthesis_core import (
    admin_display_reply_needs_enrichment,
    maybe_enrich_admin_display_reply,
    maybe_synthesize_reply,
    reply_needs_nl_synthesis,
    synthesize_user_visible_reply,
)

__all__ = [
    "SUMMARIZE_IMAGE_MARK",
    "SUMMARIZE_NEW_CONTEXT_MARK",
    "SUMMARIZE_STORED_CONTEXT_MARK",
    "VLM_GATEWAY_DOWN_META",
    "admin_display_reply_needs_enrichment",
    "admin_nl_synthesis_max_output_tokens",
    "admin_reply_already_polished",
    "context_summary_synthesis_acceptable",
    "context_summary_synthesis_evidence_char_limit",
    "context_summary_synthesis_has_useful_bullets",
    "context_summary_synthesis_max_output_tokens",
    "incoming_has_context_summarize_directive",
    "maybe_enrich_admin_display_reply",
    "maybe_synthesize_reply",
    "nl_reply_synthesis_globally_disabled",
    "repair_summarize_new_context_egress",
    "replace_bare_summarize_image_on_vlm_gateway_down",
    "replace_bare_wrong_summarize_stored_echo",
    "reply_is_trivial_for_context_summary",
    "reply_needs_nl_synthesis",
    "rescind_trivial_context_summary_reply",
    "state_evidence_for_context_summary_rescind",
    "synthesize_user_visible_reply",
    "telegram_stored_context_summary_body_when_model_trivial",
]

# Compat tests (prefijos ``_`` no forman API pública estable).
from duckclaw.egress.user_reply_nl_context_summary import (  # noqa: E402
    _deterministic_stored_context_summary,
)
