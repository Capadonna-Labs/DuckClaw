"""Tests: síntesis NL de respuesta al usuario (worker-telegram-natural-language-egress)."""

from __future__ import annotations

from unittest.mock import MagicMock

from duckclaw.forge.atoms import user_reply_nl_synthesis as mod
from duckclaw.workers.manifest import load_manifest


def test_reply_needs_nl_synthesis() -> None:
    assert mod.reply_needs_nl_synthesis('{"a": 1}') is True
    assert mod.reply_needs_nl_synthesis("[1,2]") is True
    assert mod.reply_needs_nl_synthesis("hola") is False
    assert mod.reply_needs_nl_synthesis("{broken") is False


def test_maybe_synthesize_reply_skips_when_spec_off() -> None:
    llm = MagicMock()
    spec = MagicMock()
    spec.egress_natural_language_synthesis = False
    spec.worker_id = "x"
    out = mod.maybe_synthesize_reply(llm, spec=spec, user_ask="q", reply_candidate='{"a":1}')
    assert out == '{"a":1}'
    llm.invoke.assert_not_called()


def test_maybe_synthesize_reply_invokes_llm() -> None:
    from langchain_core.messages import AIMessage

    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content="**Hola** mundo.\n\n**Siguientes pasos**\n- uno")
    spec = MagicMock()
    spec.egress_natural_language_synthesis = True
    spec.worker_id = "finanz"
    out = mod.maybe_synthesize_reply(llm, spec=spec, user_ask="cuentas", reply_candidate='[{"x":1}]')
    assert "Hola" in out
    llm.invoke.assert_called_once()


def test_load_manifest_default_egress_nl_true() -> None:
    """finanz manifest debe asumir síntesis activa sin clave explícita."""
    spec = load_manifest("finanz")
    assert spec.egress_natural_language_synthesis is True


def test_maybe_synthesize_skips_when_env_global_off(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_DISABLE_NL_REPLY_SYNTHESIS", "1")
    llm = MagicMock()
    spec = MagicMock()
    spec.egress_natural_language_synthesis = True
    spec.worker_id = "x"
    raw = '{"a": 1}'
    assert mod.maybe_synthesize_reply(llm, spec=spec, user_ask="q", reply_candidate=raw) == raw
    llm.invoke.assert_not_called()


def test_reply_is_trivial_for_context_summary() -> None:
    assert mod.reply_is_trivial_for_context_summary("Listo.") is True
    assert mod.reply_is_trivial_for_context_summary("finanz 2\n\nListo.") is True
    assert mod.reply_is_trivial_for_context_summary("finanz 2\n\n**Listo.**") is True
    assert mod.reply_is_trivial_for_context_summary("**Listo.**") is True
    assert mod.reply_is_trivial_for_context_summary("• a\n• b") is False
    assert mod.reply_is_trivial_for_context_summary("- uno\n- dos") is False
    assert mod.reply_is_trivial_for_context_summary("- solo una viñeta larga " + "x" * 30) is False


def test_state_evidence_for_context_summary_rescind_fallback_human_message() -> None:
    from langchain_core.messages import HumanMessage, SystemMessage

    mark = mod.SUMMARIZE_STORED_CONTEXT_MARK
    body = f"{mark}\n--- registro 1 ---\nx"
    st: dict = {
        "incoming": "",
        "input": "",
        "messages": [
            SystemMessage(content="sys"),
            HumanMessage(content=body),
        ],
    }
    assert mod.state_evidence_for_context_summary_rescind(st) == body


def test_state_evidence_scans_older_human_when_last_lacks_directive() -> None:
    """Regresión: un ``HumanMessage`` final sin directiva no debe impedir leer el volcado anterior."""
    from langchain_core.messages import AIMessage, HumanMessage

    mark = mod.SUMMARIZE_STORED_CONTEXT_MARK
    body = f"{mark}\n--- registro 1 ---\ny"
    st: dict = {
        "incoming": "",
        "input": "",
        "messages": [
            HumanMessage(content=body),
            HumanMessage(content="Corrección sin directiva."),
            AIMessage(content="ok"),
        ],
    }
    assert mod.state_evidence_for_context_summary_rescind(st) == body


def test_state_evidence_prefers_input_when_incoming_lacks_directive() -> None:
    mark = mod.SUMMARIZE_STORED_CONTEXT_MARK
    body = f"{mark}\n--- registro 1 ---\nz"
    st: dict = {
        "incoming": "solo título corto",
        "input": body,
        "messages": [],
    }
    assert mod.state_evidence_for_context_summary_rescind(st) == body


def test_telegram_fallback_replaces_trivial_subagent_reply() -> None:
    """Mismo caso que Telegram /context --summary + encabezado HTML separado."""
    directive = mod.SUMMARIZE_STORED_CONTEXT_MARK + "\n--- registro 1 ---\ncontenido único xyz\n"
    model = "Job-Hunter 2\n\nListo."
    out = mod.telegram_stored_context_summary_body_when_model_trivial(
        directive, model, html_header_will_duplicate_title=True
    )
    assert out is not None
    assert not out.lstrip().startswith("**Resumen del contexto")
    assert "contenido único xyz" in out


def test_telegram_fallback_skips_when_model_has_useful_bullets() -> None:
    directive = mod.SUMMARIZE_STORED_CONTEXT_MARK + "\n--- registro 1 ---\nx\n"
    model = "- Viñeta con texto suficientemente largo para no ser trivial\n"
    assert (
        mod.telegram_stored_context_summary_body_when_model_trivial(
            directive, model, html_header_will_duplicate_title=False
        )
        is None
    )


def test_rescind_llm_then_deterministic_when_synthesis_not_acceptable() -> None:
    """Si la 2.ª pasada devuelve texto corto/no sustancial, se usa el parser de registros."""
    from langchain_core.messages import AIMessage

    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content="no debe usarse")
    spec = MagicMock()
    spec.egress_natural_language_synthesis = True
    spec.worker_id = "finanz"
    inc = mod.SUMMARIZE_STORED_CONTEXT_MARK + "\n--- registro 1 ---\ntengo 23 años"
    out = mod.rescind_trivial_context_summary_reply(llm, spec, incoming=inc, reply_candidate="Listo.")
    assert "23" in out
    llm.invoke.assert_called_once()


def test_rescind_prefers_llm_prose_when_substantial_no_bullet_lines() -> None:
    """Acepta resumen en prosa (dos frases + longitud) sin viñetas ``- ``."""
    from langchain_core.messages import AIMessage

    llm = MagicMock()
    llm.invoke.return_value = AIMessage(
        content=(
            "La memoria semántica registrada indica que el usuario tiene 23 años de edad. "
            "Ese dato aparece como un hecho explícito en el volcado consultado vía /context.\n\n"
            "**Siguientes pasos**\n- Actualizar si cambia la información personal."
        )
    )
    spec = MagicMock()
    spec.egress_natural_language_synthesis = True
    spec.worker_id = "finanz"
    inc = mod.SUMMARIZE_STORED_CONTEXT_MARK + "\n--- registro 1 ---\ntengo 23 años"
    out = mod.rescind_trivial_context_summary_reply(llm, spec, incoming=inc, reply_candidate="Listo.")
    assert "23" in out
    assert "memoria semántica" in out.lower()
    llm.invoke.assert_called_once()


def test_rescind_deterministic_before_llm_and_egress_gates() -> None:
    """``llm is None`` o ``egress_natural_language_synthesis=False`` no deben bloquear el parser de registros."""
    spec = MagicMock()
    spec.egress_natural_language_synthesis = False
    spec.worker_id = "Job-Hunter"
    inc = mod.SUMMARIZE_STORED_CONTEXT_MARK + "\n--- registro 1 ---\nGemma 4 Apache 2.0\n"
    out = mod.rescind_trivial_context_summary_reply(None, spec, incoming=inc, reply_candidate="Listo.")
    assert "Gemma" in out or "Apache" in out


def test_rescind_falls_back_deterministic_when_llm_still_listo() -> None:
    """MLX a veces repite «Listo.» en la segunda pasada; una llamada y luego viñetas deterministas."""
    from langchain_core.messages import AIMessage

    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content="Listo.")
    spec = MagicMock()
    spec.egress_natural_language_synthesis = True
    spec.worker_id = "finanz"
    inc = (
        mod.SUMMARIZE_STORED_CONTEXT_MARK
        + "\n--- registro 1 (source=x) ---\ntengo 23 años\n\n"
        + "--- registro 2 (source=x) ---\nvivo en Medellín\n"
    )
    out = mod.rescind_trivial_context_summary_reply(llm, spec, incoming=inc, reply_candidate="finanz 2\n\nListo.")
    assert "23" in out
    assert "Medellín" in out
    assert "Resumen del contexto" in out
    llm.invoke.assert_called_once()


def test_deterministic_stored_context_summary_parses_registros() -> None:
    ev = (
        mod.SUMMARIZE_STORED_CONTEXT_MARK
        + "\n--- registro 1 ---\nnota A\n\n--- registro 2 ---\nhttps://example.com/x\n"
    )
    out = mod._deterministic_stored_context_summary(ev)
    assert "nota A" in out
    assert "example.com" in out


def test_context_summary_synthesis_has_useful_bullets() -> None:
    assert mod.context_summary_synthesis_has_useful_bullets("- item con texto") is True
    assert mod.context_summary_synthesis_has_useful_bullets("• otra cosa larga") is True
    assert mod.context_summary_synthesis_has_useful_bullets("- Listo.") is False
    assert mod.context_summary_synthesis_has_useful_bullets("**Solo título**\n\nListo.") is False


def test_context_summary_synthesis_acceptable_prose_or_bullets() -> None:
    long_prose = (
        "Primera frase con más de veinticuatro caracteres para el umbral de sustancia requerido. "
        "Segunda frase igualmente larga cumpliendo el mínimo de longitud total del texto completo aquí.\n\n"
        "**Siguientes pasos**\n- Uno."
    )
    assert mod.context_summary_synthesis_acceptable(long_prose) is True
    assert mod.context_summary_synthesis_acceptable("- Viñeta con texto suficientemente largo") is True
    assert mod.context_summary_synthesis_acceptable("Listo.") is False
    assert mod.context_summary_synthesis_acceptable("Solo una frase corta.") is False


def test_rescind_keeps_first_bullets_when_no_registro_dump() -> None:
    """Sin bloques ``--- registro ---`` parseables, conservar viñetas del modelo."""
    llm = MagicMock()
    spec = MagicMock()
    spec.egress_natural_language_synthesis = True
    spec.worker_id = "finanz"
    inc = mod.SUMMARIZE_STORED_CONTEXT_MARK
    cand = "• **Dato**: ya resumido con suficiente texto\n"
    out = mod.rescind_trivial_context_summary_reply(llm, spec, incoming=inc, reply_candidate=cand)
    assert out.strip() == cand.strip()
    llm.invoke.assert_not_called()


def test_rescind_runs_when_first_reply_bold_title_without_bullets() -> None:
    """Regresión: **Resumen…** + Listo. no debe hacer return antes del pipeline."""
    from langchain_core.messages import AIMessage

    llm = MagicMock()
    llm.invoke.return_value = AIMessage(content="Listo.")
    spec = MagicMock()
    spec.egress_natural_language_synthesis = True
    spec.worker_id = "Job-Hunter"
    inc = mod.SUMMARIZE_STORED_CONTEXT_MARK + "\n--- registro 1 ---\nGemma 4 nota larga\n"
    first = "**Resumen del contexto (base de datos)**\n\nListo."
    out = mod.rescind_trivial_context_summary_reply(llm, spec, incoming=inc, reply_candidate=first)
    assert "Gemma" in out or "nota" in out
    llm.invoke.assert_called_once()


def test_rescind_uses_deterministic_when_syn_only_bold_header_and_listo() -> None:
    """P≫C: MLX puede devolver título **...** + Listo.; no debe bloquear el fallback."""
    from langchain_core.messages import AIMessage

    llm = MagicMock()
    llm.invoke.return_value = AIMessage(
        content="**Resumen del contexto (base de datos)**\n\nListo."
    )
    spec = MagicMock()
    spec.egress_natural_language_synthesis = True
    spec.worker_id = "finanz"
    inc = mod.SUMMARIZE_STORED_CONTEXT_MARK + "\n--- registro 1 ---\ntengo 23 años\n"
    out = mod.rescind_trivial_context_summary_reply(llm, spec, incoming=inc, reply_candidate="Listo.")
    assert "23" in out
    assert out.count("- ") >= 1
    llm.invoke.assert_called_once()


def test_rescind_invokes_llm_when_directive_only_and_listo() -> None:
    from langchain_core.messages import AIMessage

    llm = MagicMock()
    llm.invoke.return_value = AIMessage(
        content="- **Síntesis**: texto mínimo de ocho chars\n"
    )
    spec = MagicMock()
    spec.egress_natural_language_synthesis = True
    spec.worker_id = "finanz"
    out = mod.rescind_trivial_context_summary_reply(
        llm, spec, incoming=mod.SUMMARIZE_STORED_CONTEXT_MARK, reply_candidate="Listo."
    )
    assert "Síntesis" in out
    llm.invoke.assert_called_once()
