from duckclaw_pipecat.processors.duckclaw_graph_llm import looks_like_stt_garbage


def test_whisper_loops_are_garbage() -> None:
    assert looks_like_stt_garbage("Hvadil" + "l" * 300)
    assert looks_like_stt_garbage("Hvadi" + "lI" * 120)
    assert looks_like_stt_garbage("la la la la la la la la la")  # token loop
    assert looks_like_stt_garbage("   ")


def test_real_speech_passes() -> None:
    for s in ("Usa el revisar correo.", "Hola, ¿me escuchas?", "¿Cómo va el pedido hoy? Revisa el envío.", "Sí."):
        assert not looks_like_stt_garbage(s), s
