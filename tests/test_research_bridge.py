from duckclaw.forge.skills.research_bridge import _format_tavily_results, _sanitize_tavily_text


def test_sanitize_tavily_text_removes_script_and_style_blocks() -> None:
    raw = "<div>hola</div><script>alert(1)</script><style>p{color:red}</style>mundo"
    out = _sanitize_tavily_text(raw)
    assert "<script" not in out.lower()
    assert "<style" not in out.lower()
    assert "alert(1)" not in out
    assert "hola" in out
    assert "mundo" in out


def test_sanitize_tavily_text_removes_html_tags_and_normalizes_spaces() -> None:
    raw = "<div><b>Texto</b>   con\t\tespacios</div>\n\n\n<p>linea 2</p>"
    out = _sanitize_tavily_text(raw)
    assert "<div>" not in out and "<b>" not in out and "<p>" not in out
    assert "Texto con espacios" in out
    assert "\n\n\n" not in out


def test_format_tavily_results_sanitizes_answer_title_and_content() -> None:
    payload = {
        "answer": "<script>bad()</script><b>Respuesta</b>",
        "results": [
            {
                "title": "<i>Título</i>",
                "url": "https://example.com",
                "content": "<div>contenido <script>x()</script>limpio</div>",
            }
        ],
    }
    out = _format_tavily_results(payload)
    assert "script" not in out.lower()
    assert "<b>" not in out and "<i>" not in out and "<div>" not in out
    assert "Respuesta" in out
    assert "Título" in out
    assert "contenido limpio" in out
