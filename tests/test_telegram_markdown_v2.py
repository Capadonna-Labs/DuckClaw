"""Escape MarkdownV2 y HTML para Telegram."""

from duckclaw.utils.telegram_markdown_v2 import (
    escape_telegram_html,
    escape_telegram_markdown_v2,
    llm_markdown_to_telegram_html,
    plain_subchunks_for_telegram_html,
)


def test_escape_period_for_markdown_v2() -> None:
    assert escape_telegram_markdown_v2("Listo, preparando respuesta.") == r"Listo, preparando respuesta\."


def test_escape_preserves_tg_user_link() -> None:
    raw = "[Juan](tg://user?id=1726618406) listo."
    assert escape_telegram_markdown_v2(raw) == "[Juan](tg://user?id=1726618406) listo\\."


def test_empty_string() -> None:
    assert escape_telegram_markdown_v2("") == ""


def test_escape_html_entities() -> None:
    assert escape_telegram_html("a & b < c > d") == "a &amp; b &lt; c &gt; d"


def test_escape_html_plain_prose_no_backslashes() -> None:
    s = "Listo, preparando respuesta. Precio: $1,000.41"
    assert "\\" not in escape_telegram_html(s)


def test_llm_markdown_bold_and_code_to_html() -> None:
    raw = "Hola **mundo** y `x & y`."
    html = llm_markdown_to_telegram_html(raw)
    assert "<b>mundo</b>" in html
    assert "x &amp; y" in html
    assert "<code>" not in html
    assert "**" not in html
    assert "`" not in html
    assert "\\" not in html


def test_llm_markdown_fenced_code_not_pre() -> None:
    raw = "```\na < b\n```"
    html = llm_markdown_to_telegram_html(raw)
    assert "<pre>" not in html
    assert "<code>" not in html
    assert "a &lt; b" in html


def test_llm_markdown_link_http() -> None:
    raw = "Ver [sitio](https://a.com/?q=1&r=2)"
    html = llm_markdown_to_telegram_html(raw)
    assert '<a href="https://a.com/?q=1&amp;r=2">' in html
    assert "[" not in html


def test_llm_markdown_link_tg_user_mention() -> None:
    raw = "- [Juan](tg://user?id=1726618406) (1726618406) · rol: admin"
    html = llm_markdown_to_telegram_html(raw)
    assert '<a href="tg://user?id=1726618406">' in html
    assert "Juan" in html
    assert "[" not in html
    assert "\\" not in html


def test_plain_subchunks_keeps_order() -> None:
    parts = plain_subchunks_for_telegram_html("ab" * 5000)
    assert len(parts) >= 2
    assert "".join(parts) == "ab" * 5000


def test_plain_subchunks_does_not_split_inside_fence() -> None:
    head = "intro\n\n"
    fence_body = "```\n" + ("x\n" * 400) + "```"
    tail = "\n\noutro **bold**"
    plain = head + fence_body + tail
    parts = plain_subchunks_for_telegram_html(plain, budget=500)
    assert "".join(parts) == plain
    for p in parts:
        h = llm_markdown_to_telegram_html(p)
        assert "<code>" not in h
        assert "</code>" not in h
