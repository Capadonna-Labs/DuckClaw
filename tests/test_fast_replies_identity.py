"""Tests for identity/capabilities fast-path detection."""

from __future__ import annotations

from duckclaw.commands.fast_replies import _is_capabilities_smalltalk, _is_knowledge_inventory_smalltalk


def test_identity_multi_question_triggers_fast_path() -> None:
    msg = "Hola , quie eres ? quien soy y que pudees lograr y hacer ?"
    assert _is_capabilities_smalltalk(msg) is True


def test_identity_with_knowledge_scope_preamble() -> None:
    msg = (
        "[KNOWLEDGE_SCOPE]\nAlcance RAG: Plataforma\n[/KNOWLEDGE_SCOPE]\n"
        "Hola, quien eres? quien soy y que puedes hacer?"
    )
    assert _is_capabilities_smalltalk(msg) is True


def test_concrete_sql_question_not_fast_path() -> None:
    msg = "qué puedes hacer con la tabla ventas en duckdb"
    assert _is_capabilities_smalltalk(msg) is False


def test_knowledge_inventory_question_triggers_fast_path() -> None:
    msg = "¿Qué base de conocimiento tienes?"
    assert _is_knowledge_inventory_smalltalk(msg) is True


def test_knowledge_inventory_with_empty_rag_scope() -> None:
    msg = (
        "[KNOWLEDGE_SCOPE]\nAlcance RAG: Plataforma\n[/KNOWLEDGE_SCOPE]\n"
        "Actualmente no hay documentos indexados en la base de conocimiento?"
    )
    assert _is_knowledge_inventory_smalltalk(msg) is True
