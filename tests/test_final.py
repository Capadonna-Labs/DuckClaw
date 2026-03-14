"""
Test final de smoke: valida que el monorepo DuckClaw esté operativo tras CI.

Ejecuta checks rápidos sin Redis ni servicios externos:
- DuckClaw core (DuckDB)
- LLM providers (build_llm, build_agent_graph, build_duckclaw_tools)
- API Gateway importable
- Ops / duckops básico

Uso en CI: uv run pytest tests/test_final.py -v
"""

from __future__ import annotations


def test_duckclaw_core() -> None:
    """DuckClaw core: DuckDB bridge operativo."""
    import duckclaw
    db = duckclaw.DuckClaw(":memory:")
    db.execute("CREATE TABLE _final (id INT)")
    db.execute("INSERT INTO _final VALUES (1)")
    r = db.query("SELECT * FROM _final")
    assert "1" in r
    assert db.get_version()


def test_llm_providers() -> None:
    """LLM providers: build_llm, build_agent_graph, build_duckclaw_tools."""
    import duckclaw
    from duckclaw.integrations.llm_providers import (
        build_llm,
        build_agent_graph,
        build_duckclaw_tools,
        _safe_table_name,
    )
    assert build_llm("none_llm", "", "") is None
    db = duckclaw.DuckClaw(":memory:")
    db.execute("CREATE TABLE t (id INT)")
    tools = build_duckclaw_tools(db)
    assert len(tools) >= 4
    assert _safe_table_name("ok") == "ok"
    graph = build_agent_graph(db, llm=None)
    out = graph.invoke({"incoming": "hola"})
    assert "reply" in out
    assert "hola" in out["reply"] or "Recibí" in out["reply"]


def test_api_gateway_importable() -> None:
    """API Gateway (microservicio) es importable."""
    from pathlib import Path
    import sys
    gateway_dir = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
    if gateway_dir.exists() and str(gateway_dir) not in sys.path:
        sys.path.insert(0, str(gateway_dir))
    try:
        import main as gateway_main
        assert gateway_main.app is not None
    finally:
        if str(gateway_dir) in sys.path:
            sys.path.remove(str(gateway_dir))


def test_duckops_available() -> None:
    """Duckops CLI disponible."""
    from duckclaw.ops.manager import serve
    assert callable(serve)
