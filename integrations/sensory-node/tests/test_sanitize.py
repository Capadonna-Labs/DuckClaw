from duckclaw_sensory_node.sanitize import cap_tts_text, prepare_tts_text, sanitize_tts_text


def test_sanitize_strips_markdown_and_emojis():
    raw = "**Hola** _mundo_ https://example.com/foo 😀"
    out = sanitize_tts_text(raw)
    assert "**" not in out
    assert "https://" not in out
    assert "😀" not in out
    assert "Hola" in out
    assert "mundo" in out


def test_sanitize_strips_tables_and_bullets():
    raw = """## Resumen
| Activo | Valor |
| --- | --- |
| NVDA | 100 |
- punto uno
- punto dos
"""
    out = sanitize_tts_text(raw)
    assert "|" not in out
    assert "---" not in out
    assert "##" not in out
    assert "NVDA" in out
    assert "punto uno" in out


def test_sanitize_code_blocks():
    raw = "Antes `inline` y luego:\n```python\nprint(1)\n```\nfin"
    out = sanitize_tts_text(raw)
    assert "`" not in out
    assert "print(1)" in out
    assert "Antes" in out


def test_sanitize_empty():
    assert sanitize_tts_text("") == ""


def test_cap_at_sentence():
    text = "Primera oración. Segunda oración. Tercera oración larga."
    out = cap_tts_text(text, 35)
    assert out.endswith(".")
    assert "Tercera" not in out


def test_prepare_truncates_long_plain_text():
    long_text = "Hola. " + ("Esto es una frase. " * 40)
    out = prepare_tts_text(long_text, max_chars=120)
    assert len(out) <= 120
    assert "Hola" in out
