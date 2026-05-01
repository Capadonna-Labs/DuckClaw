"""Búsqueda VSS híbrida (vector opcional + léxico)."""

from __future__ import annotations

import json

import duckdb
import pytest

from duckclaw.forge.atoms.semantic_memory_hybrid import fetch_semantic_rows_lexical, lexical_tokens


def test_lexical_tokens_strips_stops():
    ts = lexical_tokens("busca insights sobre inflación META")
    assert any("infl" in x for x in ts)
    assert "busca" not in ts


def test_lexical_finds_pending_row(tmp_path):
    dbf = tmp_path / "s.duckdb"
    con = duckdb.connect(str(dbf))
    con.execute(
        """
        CREATE TABLE main.semantic_memory (
            id VARCHAR PRIMARY KEY,
            content TEXT NOT NULL,
            source VARCHAR DEFAULT 'manual',
            embedding FLOAT[384],
            embedding_status VARCHAR DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        "INSERT INTO main.semantic_memory (id, content, source, embedding, embedding_status) "
        "VALUES ('a1', 'Perfil inversionista conservative max drawdown 5%', 'ctx', NULL, 'PENDING')"
    )
    con.close()

    class _Db:
        def query(self, sql: str) -> str:
            c2 = duckdb.connect(str(dbf), read_only=True)
            try:
                r = c2.execute(sql).fetchall()
                n = [d[0] for d in c2.description]
                out = [dict(zip(n, row)) for row in r]
                return json.dumps(out, ensure_ascii=False)
            finally:
                c2.close()

    db = _Db()
    hits = fetch_semantic_rows_lexical(db, query="investor conservative drawdown", limit=5)
    assert hits and "conservative" in (hits[0].get("content") or "").lower()
