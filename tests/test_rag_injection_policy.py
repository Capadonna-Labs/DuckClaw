from __future__ import annotations

from duckclaw.forge.rag.injection_policy import should_inject_playground_context


def test_meta_capabilities_skips_rag_injection() -> None:
    assert should_inject_playground_context("¿Qué puedes hacer?") is False
    assert (
        should_inject_playground_context(
            "Que puedes hacer ? que documentos tienes disponibles ? "
            "tienes alglun documento en formato .docx ?"
        )
        is False
    )


def test_concrete_task_still_injects_rag() -> None:
    assert (
        should_inject_playground_context(
            "Resume el informe mensual de junio usando los KPIs del vault"
        )
        is True
    )
