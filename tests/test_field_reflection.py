"""Tests: Finanz field reflection (tool errors, beliefs upsert, experiencia de campo)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from duckclaw.workers.field_reflection import (
    finanz_field_reflection_enabled,
    format_field_experience_block,
    last_tool_batch_has_error,
    lesson_belief_key,
    parse_reflection_json,
    persist_field_lesson,
    tool_content_indicates_error,
)
from duckclaw.workers.manifest import WorkerSpec


def _finanz_spec() -> WorkerSpec:
    return WorkerSpec(
        worker_id="finanz",
        logical_worker_id="finanz",
        name="Finanz",
        schema_name="finance_worker",
        llm_required=None,
        temperature=0.2,
        topology="general",
        skills_list=[],
        allowed_tables=[],
        read_only=False,
        worker_dir=Path("."),
        field_reflection_config={"enabled": True},
    )


def test_finanz_field_reflection_enabled() -> None:
    assert finanz_field_reflection_enabled(_finanz_spec()) is True
    s2 = _finanz_spec()
    s2.field_reflection_config = {"enabled": False}
    assert finanz_field_reflection_enabled(s2) is False
    other = _finanz_spec()
    other.logical_worker_id = "other"
    assert finanz_field_reflection_enabled(other) is False


def test_tool_content_indicates_error() -> None:
    assert tool_content_indicates_error("Error: boom", "x") is True
    assert tool_content_indicates_error('{"error": "LAKE_EMPTY_BARS"}', "fetch_market_data") is True
    assert tool_content_indicates_error('{"exit_code": 1}', "run_sandbox") is True
    assert tool_content_indicates_error('{"exit_code": 0}', "run_sandbox") is False
    assert tool_content_indicates_error('{"status": "ok"}', "x") is False


def test_last_tool_batch_has_error() -> None:
    from langchain_core.messages import AIMessage, ToolMessage

    msgs = [
        AIMessage(content="x", tool_calls=[{"name": "fetch_market_data", "id": "1", "args": {}}]),
        ToolMessage(content='{"error": "LAKE_EMPTY_BARS"}', tool_call_id="1", name="fetch_market_data"),
    ]
    assert last_tool_batch_has_error(msgs) is True

    msgs2 = [
        AIMessage(content="x", tool_calls=[{"name": "read_sql", "id": "1", "args": {}}]),
        ToolMessage(content="[]", tool_call_id="1", name="read_sql"),
    ]
    assert last_tool_batch_has_error(msgs2) is False


def test_parse_reflection_json() -> None:
    raw = '{"context_trigger": "fetch_market_data LAKE_EMPTY", "lesson_text": "Verificar parquet en VPS.", "confidence_score": 1.5}'
    p = parse_reflection_json(raw)
    assert p is not None
    assert p["context_trigger"].startswith("fetch_market_data")
    assert "VPS" in p["lesson_text"]
    assert p["confidence_score"] == 1.5
    wrapped = "```json\n" + raw + "\n```"
    assert parse_reflection_json(wrapped) is not None


def test_lesson_belief_key_stable() -> None:
    k1 = lesson_belief_key("a", "b")
    k2 = lesson_belief_key("a", "b")
    assert k1 == k2 and k1.startswith("lesson_")


def test_persist_field_lesson_upsert_confidence_monotone() -> None:
    try:
        import duckclaw
    except ImportError:
        pytest.skip("duckclaw not available")
    db = duckclaw.DuckClaw(":memory:")
    db.execute("CREATE SCHEMA finance_worker")
    db.execute(
        """
        CREATE TABLE finance_worker.agent_beliefs (
            belief_key VARCHAR PRIMARY KEY,
            target_value REAL NOT NULL,
            observed_value REAL,
            threshold REAL NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            belief_kind VARCHAR,
            context_trigger VARCHAR,
            lesson_text VARCHAR,
            confidence_score DOUBLE
        )
        """
    )
    bk = lesson_belief_key("t", "lesson one")
    persist_field_lesson(db, "finance_worker", bk, "t", "lesson one", 1.0)
    persist_field_lesson(db, "finance_worker", bk, "t", "new text ignored", 3.0)
    r = json.loads(db.query("SELECT confidence_score, lesson_text FROM finance_worker.agent_beliefs"))
    assert len(r) == 1
    assert float(r[0]["confidence_score"]) == 3.0
    assert r[0]["lesson_text"] == "lesson one"


def test_format_field_experience_block() -> None:
    try:
        import duckclaw
    except ImportError:
        pytest.skip("duckclaw not available")
    db = duckclaw.DuckClaw(":memory:")
    db.execute("CREATE SCHEMA finance_worker")
    db.execute(
        """
        CREATE TABLE finance_worker.agent_beliefs (
            belief_key VARCHAR PRIMARY KEY,
            target_value REAL NOT NULL,
            observed_value REAL,
            threshold REAL NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            belief_kind VARCHAR,
            context_trigger VARCHAR,
            lesson_text VARCHAR,
            confidence_score DOUBLE
        )
        """
    )
    persist_field_lesson(
        db,
        "finance_worker",
        lesson_belief_key("TSLA lake", "empty bars"),
        "TSLA lake empty",
        "Si LAKE_EMPTY_BARS, revisar parquet en Capadonna.",
        2.0,
    )
    block = format_field_experience_block("precio de TSLA y lake", db, "finance_worker", 5)
    assert "Experiencia de Campo" in block
    assert "TSLA" in block or "lake" in block.lower()
