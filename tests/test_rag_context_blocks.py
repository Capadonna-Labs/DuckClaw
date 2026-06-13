from __future__ import annotations

from duckclaw.forge.rag.context_blocks import (
    extract_tagged_block,
    preserve_context_blocks_for_worker,
    strip_tagged_blocks,
)


def test_extract_and_strip_tagged_blocks() -> None:
    text = (
        "Pregunta inicial\n"
        "[RAG_CONTEXT]\n"
        "Clean Code habla de nombres claros.\n"
        "[/RAG_CONTEXT]\n"
        "Pregunta final"
    )

    assert (
        extract_tagged_block(text, "RAG_CONTEXT")
        == "[RAG_CONTEXT]\nClean Code habla de nombres claros.\n[/RAG_CONTEXT]"
    )
    assert strip_tagged_blocks(text, ("RAG_CONTEXT",)) == "Pregunta inicial\n\nPregunta final"


def test_preserve_context_blocks_uses_user_question_for_rag_turns() -> None:
    incoming = (
        "[RAG_SOURCE_INVENTORY]\n"
        "- Clean Code (active): 1 docs, 3 chunks, tipo=pdf\n"
        "[/RAG_SOURCE_INVENTORY]\n"
        "[RAG_CONTEXT]\n"
        "Usa nombres que revelen intención.\n"
        "[/RAG_CONTEXT]\n"
        "Qué dice Clean Code sobre nombres?"
    )

    task = preserve_context_blocks_for_worker(
        incoming,
        "Inspecciona la base DuckDB antes de responder.",
        explicit_storage_request=lambda _text: False,
    )

    assert task.startswith("[RAG_SOURCE_INVENTORY]\n")
    assert "[RAG_CONTEXT]\nUsa nombres que revelen intención.\n[/RAG_CONTEXT]" in task
    assert "[WORKER_TASK]\n\nQué dice Clean Code sobre nombres?\n\n[/WORKER_TASK]" in task
    assert "Inspecciona la base DuckDB" not in task


def test_preserve_context_blocks_keeps_planned_task_for_storage_intent() -> None:
    incoming = (
        "[RAG_CONTEXT]\n"
        "Contexto recuperado.\n"
        "[/RAG_CONTEXT]\n"
        "Qué tablas tengo en DuckDB?"
    )

    task = preserve_context_blocks_for_worker(
        incoming,
        "Lista las tablas disponibles en DuckDB.",
        explicit_storage_request=lambda text: "tablas" in text.lower(),
    )

    assert "[RAG_CONTEXT]\nContexto recuperado.\n[/RAG_CONTEXT]" in task
    assert "[WORKER_TASK]\n\nLista las tablas disponibles en DuckDB.\n\n[/WORKER_TASK]" in task
