"""Superficie url_research: sin GitHub/Reddit en cold start para MQL5."""

from __future__ import annotations

import pytest

from duckclaw.graphs.manager_graph import (
    _LONE_HTTP_URL_ONLY_LINE,
    _worker_should_use_url_research_mcp_surface,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://www.mql5.com/es/code/12345", True),
        ("https://www.reddit.com/r/foo/comments/abc/", True),
        ("https://example.com/article", True),
        ("genera una imagen de un pato", False),
        ("[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]\nhttps://x.com/a", False),
        ("resumen mercado SPX hoy", False),
    ],
)
def test_worker_url_research_surface(text: str, expected: bool) -> None:
    assert _worker_should_use_url_research_mcp_surface(text) is expected


def test_lone_https_url_regex() -> None:
    assert _LONE_HTTP_URL_ONLY_LINE.match("https://www.mql5.com/es/code/1")
    assert not _LONE_HTTP_URL_ONLY_LINE.match("lee https://www.mql5.com/es/code/1")


def test_build_worker_graph_url_research_skips_github_reddit_mql5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MQL5 solo URL: no registra bridges stdio pesados."""
    registered: dict[str, bool] = {"github": False, "reddit": False, "trends": False}

    def _fake_github(tools_list: list, *_a: object, **_k: object) -> None:
        registered["github"] = True

    def _fake_reddit(tools_list: list, *_a: object, **_k: object) -> None:
        registered["reddit"] = True

    def _fake_trends(tools_list: list, *_a: object, **_k: object) -> None:
        registered["trends"] = True

    monkeypatch.setattr(
        "duckclaw.forge.skills.github_bridge.register_github_skill",
        _fake_github,
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.reddit_bridge.register_reddit_skill",
        _fake_reddit,
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.google_trends_bridge.register_google_trends_skill",
        _fake_trends,
    )
    monkeypatch.setattr(
        "duckclaw.workers.factory._build_worker_tools",
        lambda _db, _spec: [],
    )
    monkeypatch.setattr(
        "duckclaw.workers.factory.load_system_prompt",
        lambda _spec: "test",
    )
    monkeypatch.setattr(
        "duckclaw.workers.factory._apply_forge_attaches",
        lambda *a, **k: None,
    )
    monkeypatch.setenv("DUCKCLAW_LLM_PROVIDER", "none_llm")

    from duckclaw.workers.factory import build_worker_graph

    build_worker_graph(
        "Quant-Trader",
        None,
        None,
        tool_surface="url_research",
        incoming_hint="https://www.mql5.com/es/code/99",
    )
    assert registered["github"] is False
    assert registered["reddit"] is False
    assert registered["trends"] is False


def test_build_worker_graph_url_research_registers_reddit_for_reddit_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reddit solo URL: registra MCP reddit (no Tavily sustituto)."""
    registered: dict[str, bool] = {"reddit": False}

    def _fake_reddit(tools_list: list, *_a: object, **_k: object) -> None:
        registered["reddit"] = True

    monkeypatch.setattr(
        "duckclaw.forge.skills.reddit_bridge.register_reddit_skill",
        _fake_reddit,
    )
    monkeypatch.setattr(
        "duckclaw.workers.factory._build_worker_tools",
        lambda _db, _spec: [],
    )
    monkeypatch.setattr(
        "duckclaw.workers.factory.load_system_prompt",
        lambda _spec: "test",
    )
    monkeypatch.setattr(
        "duckclaw.workers.factory._apply_forge_attaches",
        lambda *a, **k: None,
    )
    monkeypatch.setenv("DUCKCLAW_LLM_PROVIDER", "none_llm")

    from duckclaw.workers.factory import build_worker_graph

    build_worker_graph(
        "Quant-Trader",
        None,
        None,
        tool_surface="url_research",
        incoming_hint="https://www.reddit.com/r/test/comments/abc/",
    )
    assert registered["reddit"] is True
