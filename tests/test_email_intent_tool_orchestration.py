"""Email intent detection, targeted Gmail query, and MCP tool resolution."""

from __future__ import annotations

from duckclaw.workers.tool_orchestration import (
    build_gmail_targeted_query,
    find_gmail_mcp_search_tool,
    format_email_directive,
    incoming_has_email_intent,
    incoming_has_email_screenshot,
    try_targeted_email_fast_plan,
)


def test_incoming_has_email_intent_spanish() -> None:
    assert incoming_has_email_intent("busca el correo y saca insights")
    assert incoming_has_email_intent("revisa mi bandeja de entrada")
    assert not incoming_has_email_intent("analiza esta imagen")


def test_incoming_has_email_screenshot_with_vlm_failure() -> None:
    text = (
        "busca el correo y saca insights\n\n"
        "[Nota: visión (VLM) no disponible; las imágenes quedaron guardadas]\n"
        "[IMAGENES_ADJUNTAS] imagen_1 → /vault/inbound/x.png"
    )
    assert incoming_has_email_screenshot(text)


def test_build_gmail_targeted_query_from_vlm_labels() -> None:
    text = (
        "busca el correo\n\n"
        "Contexto visual adjunto: Remitente: Data Points. "
        'Asunto: "DeepSeek V4 Flash rivals Gemini"\n'
        "[VLM_CONTEXT image_hash=abc confidence=0.9]"
    )
    q = build_gmail_targeted_query(text)
    assert q is not None
    assert "subject:" in q
    assert "DeepSeek" in q


def test_format_email_directive_blocks_inbox_when_vlm_down() -> None:
    text = (
        "busca el correo\n\n"
        "[Nota: visión (VLM) no disponible]\n"
        "[IMAGENES_ADJUNTAS] imagen_1 → /vault/x.png"
    )
    directive = format_email_directive(text)
    assert "NO escanees toda la bandeja" in directive
    assert "VLM no está disponible" in directive


def test_try_targeted_email_fast_plan_on_screenshot_without_vlm() -> None:
    text = (
        "busca el correo y saca insights\n\n"
        "[Nota: visión (VLM) falló]\n"
        "[IMAGENES_ADJUNTAS] imagen_1 → /vault/x.png"
    )
    plan = try_targeted_email_fast_plan(text)
    assert plan is not None
    title, tasks, planned, _ov = plan
    assert "NO escanees bandeja" in tasks[0]
    assert "[EMAIL_SCREENSHOT]" in planned


def test_try_targeted_email_fast_plan_skips_plain_text() -> None:
    assert try_targeted_email_fast_plan("busca el correo y saca insights") is None


def test_build_gmail_targeted_query_strips_markdown_noise() -> None:
    text = (
        "Contexto visual adjunto: Remitente: ** Data Points. "
        'Asunto: "** DeepSeek V4 Flash rivals Gemini"\n'
        "[VLM_CONTEXT image_hash=x confidence=0.8]"
    )
    q = build_gmail_targeted_query(text)
    assert q is not None
    assert "**" not in q


def test_find_gmail_mcp_search_tool_prefers_gmail_named() -> None:
    tools = {
        "mcp__notion__search_threads": object(),
        "mcp__google_gmail__search_threads": object(),
    }
    assert find_gmail_mcp_search_tool(tools) == "mcp__google_gmail__search_threads"


def test_find_gmail_mcp_search_tool_single_candidate() -> None:
    tools = {"mcp__abc123__search_threads": object()}
    assert find_gmail_mcp_search_tool(tools) == "mcp__abc123__search_threads"
