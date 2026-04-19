from duckclaw.forge.skills.research_bridge import (
    _format_tavily_results,
    _hostname_from_domain_spec,
    _normalize_include_domains,
)


def test_hostname_from_domain_spec_strips_www_and_path() -> None:
    assert _hostname_from_domain_spec("https://www.medellin.gov.co/es/pqrsd/") == "medellin.gov.co"
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
