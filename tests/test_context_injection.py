"""Tests mínimos: CONTEXT_INJECTION delta, chunking, writer sync."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]


def test_context_injection_delta_pydantic_roundtrip() -> None:
    sys.path.insert(0, str(_REPO / "services" / "api-gateway"))
    from core.context_injection_delta import (  # noqa: PLC0415
        ContextInjectionStateDelta,
        build_context_injection_delta,
    )

    d = build_context_injection_delta(
        tenant_id="Finanzas",
        raw_text="nota técnica",
        user_id="42",
        target_db_path="/tmp/x.duckdb",
    )
    raw = d.model_dump_json()
    back = ContextInjectionStateDelta.model_validate_json(raw)
    assert back.delta_type == "CONTEXT_INJECTION"
    assert back.mutation.raw_text == "nota técnica"
    assert back.user_id == "42"


def test_chunk_context_raw_text_splits_paragraphs() -> None:
    sys.path.insert(0, str(_REPO / "services" / "db-writer"))
    from context_injection_handler import chunk_context_raw_text  # noqa: PLC0415

    big = "a" * 5000 + "\n\n" + "b" * 5000
    parts = chunk_context_raw_text(big, max_chunk=8000)
    assert len(parts) >= 2
    assert all(len(p) <= 8000 for p in parts)


def test_sync_context_injection_inserts_row(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sys.path.insert(0, str(_REPO / "services" / "db-writer"))
    import duckclaw.vaults as vaults_mod

    monkeypatch.setattr(vaults_mod, "db_root", lambda: tmp_path)
    priv = tmp_path / "private" / "u1"
    priv.mkdir(parents=True)
    dbf = priv / "finanz.duckdb"

    def _fake_embed(_t: str) -> list[float]:
        return [0.01] * 384

    monkeypatch.setattr("duckclaw.forge.rag.embeddings.embed_text", _fake_embed)

    from context_injection_handler import _sync_handle_context_injection  # noqa: PLC0415

    msg = json.dumps(
        {
            "tenant_id": "default",
            "delta_type": "CONTEXT_INJECTION",
            "mutation": {"raw_text": "alpha bravo", "source": "telegram_cmd"},
            "user_id": "u1",
            "target_db_path": str(dbf.resolve()),
        }
    )
    events = _sync_handle_context_injection(msg)
    assert isinstance(events, list)
    import duckdb

    con = duckdb.connect(str(dbf), read_only=True)
    try:
        n = con.execute("SELECT count(*) FROM main.semantic_memory").fetchone()[0]
        assert int(n) >= 1
        st = con.execute(
            "SELECT embedding_status FROM main.semantic_memory LIMIT 1"
        ).fetchone()[0]
        assert str(st).upper() == "READY"
    finally:
        con.close()


def test_parse_context_add_command() -> None:
    sys.path.insert(0, str(_REPO / "services" / "api-gateway"))
    from routers.telegram_inbound_webhook import (  # noqa: PLC0415
        _parse_context_add_command,
        _parse_context_summary_command,
    )

    assert _parse_context_add_command("/foo") == (False, "")
    ok, body = _parse_context_add_command("/context --add hello")
    assert ok and body == "hello"
    ok2, body2 = _parse_context_add_command("/context@MyBot --add  line ")
    assert ok2 and body2 == "line"

    assert _parse_context_summary_command("/context --summary") is True
    assert _parse_context_summary_command("/context --summarize") is True
    assert _parse_context_summary_command("/context@Bot --peek") is True
    assert _parse_context_summary_command("/context --db") is True
    assert _parse_context_summary_command("/context --add x") is False


def test_fetch_semantic_memory_snapshot_empty_and_rows(tmp_path: Path) -> None:
    sys.path.insert(0, str(_REPO / "services" / "api-gateway"))
    from core.context_stored_snapshot import fetch_semantic_memory_snapshot  # noqa: PLC0415

    missing = tmp_path / "nope.duckdb"
    assert fetch_semantic_memory_snapshot(str(missing)) == ""

    import duckdb

    dbf = tmp_path / "v.duckdb"
    con = duckdb.connect(str(dbf))
    try:
        con.execute(
            """
            CREATE TABLE main.semantic_memory (
                id VARCHAR PRIMARY KEY,
                content TEXT NOT NULL,
                source VARCHAR DEFAULT 'manual_injection',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.execute(
            "INSERT INTO main.semantic_memory (id, content) VALUES ('a', 'hello snapshot')"
        )
    finally:
        con.close()

    out = fetch_semantic_memory_snapshot(str(dbf), max_rows=10, max_chars=5000)
    assert "hello snapshot" in out
    assert "registro" in out


def test_fetch_semantic_memory_snapshot_ephemeral_after_stale_reuse(tmp_path: Path) -> None:
    """Reuse vacío no debe cortar: otra conexión RO debe ver filas escritas en disco (p. ej. db-writer)."""
    sys.path.insert(0, str(_REPO / "services" / "api-gateway"))
    from core.context_stored_snapshot import fetch_semantic_memory_snapshot  # noqa: PLC0415

    import duckdb

    dbf = tmp_path / "stale.duckdb"
    con = duckdb.connect(str(dbf))
    try:
        con.execute(
            """
            CREATE TABLE main.semantic_memory (
                id VARCHAR PRIMARY KEY,
                content TEXT NOT NULL,
                source VARCHAR DEFAULT 'manual_injection',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.execute(
            "INSERT INTO main.semantic_memory (id, content) VALUES ('x', 'ephemeral sees this')"
        )
    finally:
        con.close()

    class _StaleReuse:
        _path = str(dbf.resolve())

        def query(self, _sql: str) -> str:
            return "[]"

    out = fetch_semantic_memory_snapshot(
        str(dbf),
        max_rows=10,
        max_chars=5000,
        reuse_readonly_connection=_StaleReuse(),
    )
    assert "ephemeral sees this" in out
    assert "registro" in out
