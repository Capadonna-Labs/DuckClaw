"""Tests: UnifiedMemoryOrchestrator and tenant vault smoke checks."""

from __future__ import annotations

import json

def test_classify_memory_route_prefers_sql_for_conteo():
    from duckclaw.forge.skills.unified_memory_orchestrator import classify_memory_route

    r = classify_memory_route("¿Cuántos roles hay en el sistema?")
    assert "sql" in r


def test_run_unified_memory_returns_valid_json():
    from duckclaw.forge.skills.unified_memory_orchestrator import run_unified_memory

    class _Dummy:
        def execute(self, *_a, **_k):
            return None

        def query(self, sql: str, *_a, **_k):
            _ = sql
            return "[]"

    out = run_unified_memory(_Dummy(), "conteo de roles")
    data = json.loads(out)
    assert set(data.keys()) == {"sql_data", "graph_relations", "semantic_matches"}
    assert isinstance(data["sql_data"], list)


def test_ensure_tenant_industry_db_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from duckclaw.vaults import ensure_tenant_industry_db

    p = ensure_tenant_industry_db("acme_corp")
    assert p.name == "default.duckdb"
    assert "private" in str(p).replace("\\", "/")
    assert p.is_file()
