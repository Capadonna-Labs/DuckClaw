from duckclaw_sensory_node.sanitize import sanitize_tts_text


def test_sanitize_strips_markdown_and_emojis():
    raw = "**Hola** _mundo_ https://example.com/foo 😀"
    out = sanitize_tts_text(raw)
    assert "**" not in out
    assert "_" not in out or "mundo" in out
    assert "https://" not in out
    assert "😀" not in out
    assert "Hola" in out


def test_sanitize_empty():
    assert sanitize_tts_text("") == ""
