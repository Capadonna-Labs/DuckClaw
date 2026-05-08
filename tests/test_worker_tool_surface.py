"""build_worker_graph: tool_surface context_synthesis omite bridges MCP stdio."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def finanz_db_path(tmp_path: Path) -> str:
    p = tmp_path / "finanz_tool_surface.duckdb"
    return str(p)


def test_build_worker_graph_context_synthesis_skips_stdio_mcp_registers(
    finanz_db_path: str,
) -> None:
    """Modo síntesis: omite GitHub y Google Trends; Reddit sí (URLs /context Reddit)."""
    from duckclaw import DuckClaw
    from duckclaw.workers.factory import build_worker_graph

    db = DuckClaw(finanz_db_path)

    class _StubLLM:
        def bind_tools(self, tools: list, **_kwargs):
            return self

        def invoke(self, *_args, **_kwargs):
            return type("R", (), {"content": "ok"})()

    with (
        patch("duckclaw.forge.skills.github_bridge.register_github_skill") as m_gh,
        patch("duckclaw.forge.skills.reddit_bridge.register_reddit_skill") as m_rd,
        patch(
            "duckclaw.forge.skills.google_trends_bridge.register_google_trends_skill"
        ) as m_gt,
    ):
        build_worker_graph(
            "finanz",
            finanz_db_path,
            _StubLLM(),
            reuse_db=db,
            tool_surface="context_synthesis",
        )
        m_gh.assert_not_called()
        m_rd.assert_called_once()
        m_gt.assert_not_called()


def test_build_worker_graph_full_calls_mcp_registers_when_manifest_has_them(
    finanz_db_path: str,
) -> None:
    """Modo full: los registros se intentan (finanz declara reddit / google_trends en manifest)."""
    from duckclaw import DuckClaw
    from duckclaw.workers.factory import build_worker_graph

    db = DuckClaw(finanz_db_path)

    class _StubLLM:
        def bind_tools(self, tools: list, **_kwargs):
            return self

        def invoke(self, *_args, **_kwargs):
            return type("R", (), {"content": "ok"})()

    with (
        patch("duckclaw.forge.skills.github_bridge.register_github_skill") as m_gh,
        patch("duckclaw.forge.skills.reddit_bridge.register_reddit_skill") as m_rd,
        patch(
            "duckclaw.forge.skills.google_trends_bridge.register_google_trends_skill"
        ) as m_gt,
    ):
        build_worker_graph(
            "finanz",
            finanz_db_path,
            _StubLLM(),
            reuse_db=db,
            tool_surface="full",
        )
        # finanz manifest tiene reddit y google_trends; github solo si está en manifest
        m_rd.assert_called_once()
        m_gt.assert_called_once()


@pytest.fixture
def isolated_finanz_db_path(tmp_path: Path) -> str:
    """Archivo distinto del ``reuse_db`` del manager para no mezclar RW+RO en el mismo PID."""
    p = tmp_path / "finanz_summarize_ro.duckdb"
    return str(p)


def test_build_worker_graph_summarize_directive_opens_vault_read_only(
    isolated_finanz_db_path: str,
) -> None:
    """SUMMARIZE_* debe abrir la bóveda RO (evita lock vs db-writer durante context injection)."""
    from duckclaw import DuckClaw
    from duckclaw.workers.factory import build_worker_graph

    class _StubLLM:
        def bind_tools(self, tools: list, **_kwargs):
            return self

        def invoke(self, *_args, **_kwargs):
            return type("R", (), {"content": "ok"})()

    opened: list[tuple[bool, ...]] = []

    real_dc = DuckClaw
    _bootstrap = DuckClaw(isolated_finanz_db_path)
    _bootstrap.close()

    def _tracking_dc(path: str, read_only: bool = False, **kwargs: object):
        opened.append((bool(read_only),))
        return real_dc(path, read_only=read_only, **kwargs)

    with patch("duckclaw.DuckClaw", side_effect=_tracking_dc):
        build_worker_graph(
            "finanz",
            isolated_finanz_db_path,
            _StubLLM(),
            tool_surface="context_synthesis",
            open_vault_read_only=True,
        )
    assert any(ro is True for (ro,) in opened), "expected at least one DuckClaw(..., read_only=True)"
