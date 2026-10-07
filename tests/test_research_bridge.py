from duckclaw.forge.skills.local_web_search import (
    _host_from_domain_spec,
    _normalize_include_domains as _local_normalize_domains,
    format_search_results,
    local_search_backend,
)
from duckclaw.forge.skills.research_bridge import (
    _format_tavily_results,
    _hostname_from_domain_spec,
    _normalize_include_domains,
)


def test_hostname_from_domain_spec_strips_www_and_path() -> None:
    assert _hostname_from_domain_spec("https://www.medellin.gov.co/es/tramites/") == "medellin.gov.co"
    assert _hostname_from_domain_spec("medellin.gov.co") == "medellin.gov.co"
    assert _hostname_from_domain_spec("www.medellin.gov.co/foo") == "medellin.gov.co"


def test_normalize_include_domains_dedupes() -> None:
    assert _normalize_include_domains(
        ["https://www.medellin.gov.co/a", "www.medellin.gov.co/b", "medellin.gov.co"]
    ) == ["medellin.gov.co"]


def test_normalize_include_domains_empty() -> None:
    assert _normalize_include_domains(None) == []
    assert _normalize_include_domains([]) == []


def test_format_tavily_results_basic_dict() -> None:
    payload = {
        "answer": "Respuesta corta",
        "results": [
            {
                "title": "Título",
                "url": "https://medellin.gov.co/x",
                "content": "contenido",
            }
        ],
    }
    out = _format_tavily_results(payload)
    assert "Respuesta corta" in out
    assert "Título" in out
    assert "medellin.gov.co" in out
    assert "contenido" in out


def test_local_search_backend_default_is_ddg(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_SEARXNG_URL", raising=False)
    assert local_search_backend() == "duckduckgo"


def test_local_search_backend_searxng(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_SEARXNG_URL", "http://127.0.0.1:8080/")
    assert local_search_backend() == "searxng"


def test_format_local_search_results() -> None:
    out = format_search_results(
        [{"title": "A", "url": "https://example.com", "content": "hola"}],
        backend="duckduckgo",
    )
    assert "duckduckgo" in out
    assert "example.com" in out
    assert "hola" in out


def test_register_research_skill_adds_web_search_without_tavily(
    monkeypatch,
) -> None:
    from duckclaw.forge.skills.research_bridge import register_research_skill

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(
        "duckclaw.forge.skills.research_bridge._tavily_available",
        lambda **_k: False,
    )
    tools: list = []
    register_research_skill(
        tools,
        {
            "local_search_enabled": True,
            "tavily_enabled": True,
            "max_results": 3,
        },
    )
    names = [getattr(t, "name", "") for t in tools]
    assert "web_search" in names
    assert "tavily_search" not in names



def test_tavily_extract_reads_one_url_and_truncates(monkeypatch) -> None:
    import sys
    import types

    from duckclaw.forge.skills import research_bridge as rb

    calls: list = []

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            pass

        def extract(self, urls):
            calls.append(urls)
            return {"results": [{"url": urls[0], "raw_content": "x" * (rb._EXTRACT_MAX_CHARS + 5)}]}

    monkeypatch.setitem(sys.modules, "tavily", types.SimpleNamespace(TavilyClient=FakeClient))
    monkeypatch.setattr(rb, "_resolve_tavily_api_key", lambda **_: "k")
    tool = rb._tavily_extract_tool({})
    out = tool.invoke({"url": "https://ir.acme.com/q1"})
    assert calls == [["https://ir.acme.com/q1"]]
    assert "[truncado" in out and out.count("x") == rb._EXTRACT_MAX_CHARS
    assert "inválida" in tool.invoke({"url": "file:///etc/passwd"})
    assert rb._tavily_extract_tool({"tavily_extract_enabled": False}) is None
