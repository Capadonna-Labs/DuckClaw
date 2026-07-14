"""Tests for MCP connector preset loader and worker runtime grant wiring."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import duckdb
import pytest

from duckclaw.mcp_connector_presets import (
    bundled_mcp_connector_presets_path,
    clear_mcp_connector_presets_cache,
    list_mcp_connector_presets,
    load_mcp_connector_presets,
    preset_payload,
    resolve_mcp_connector_presets_path,
)
from duckclaw.schema_migrations import run_pending_migrations
from duckclaw.write_handlers.mcp_connectors import (
    _apply_grant_worker_mcp_connector,
    _apply_upsert_mcp_connector,
)


@pytest.fixture(autouse=True)
def _clear_presets_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_MCP_PRESETS_PATH", raising=False)
    monkeypatch.delenv("DUCKCLAW_REPO_ROOT", raising=False)
    clear_mcp_connector_presets_cache()
    yield
    clear_mcp_connector_presets_cache()


def test_bundled_presets_path_points_at_seeds_yaml() -> None:
    path = bundled_mcp_connector_presets_path()
    assert path.name == "mcp_connector_presets.yaml"
    assert path.is_file()


def test_stdio_profile_merges_into_preset() -> None:
    payload = preset_payload("mcp_fetch")
    assert payload is not None
    assert payload["transport"] == "stdio"
    assert payload["launch_command"] == "npx"
    assert payload["read_only"] is True
    assert payload["auth_kind"] == "none"
    assert payload["launch_args"] == ["-y", "@modelcontextprotocol/server-fetch"]
    assert payload["tool_allowlist"] == ["*"]


def test_env_override_loads_custom_presets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custom = tmp_path / "custom_presets.yaml"
    custom.write_text(
        """
defaults:
  tool_allowlist: ["ping"]
presets:
  custom_ping:
    display_name: Custom Ping
    transport: streamable_http
    endpoint_url: https://example.test/mcp
    egress_hosts: [example.test]
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("DUCKCLAW_MCP_PRESETS_PATH", str(custom))
    clear_mcp_connector_presets_cache()

    presets = load_mcp_connector_presets()
    assert list(presets.keys()) == ["custom_ping"]
    row = preset_payload("custom_ping")
    assert row is not None
    assert row["tool_allowlist"] == ["ping"]
    assert row["endpoint_url"] == "https://example.test/mcp"


def test_repo_root_config_override_when_present(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "mcp_connector_presets.yaml").write_text(
        """
presets:
  repo_only:
    display_name: Repo Only
    transport: streamable_http
    endpoint_url: https://repo.test/mcp
    egress_hosts: [repo.test]
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    clear_mcp_connector_presets_cache()

    assert resolve_mcp_connector_presets_path() == (config_dir / "mcp_connector_presets.yaml").resolve()
    assert "repo_only" in load_mcp_connector_presets()


def test_list_mcp_connector_presets_includes_all_bundled_ids() -> None:
    presets = {p["preset_id"]: p for p in list_mcp_connector_presets()}
    assert {
        "remote_http_oauth",
        "notion",
        "google_workspace",
        "google_calendar",
        "google_maps",
        "tavily",
        "github",
        "mcp_fetch",
        "mcp_time",
    }.issubset(presets)


def test_tavily_preset_is_remote_bearer() -> None:
    payload = preset_payload("tavily")
    assert payload is not None
    assert payload["transport"] == "streamable_http"
    assert payload["endpoint_url"] == "https://mcp.tavily.com/mcp/"
    assert payload["auth_kind"] == "bearer"
    assert "mcp.tavily.com" in payload["egress_hosts"]
    assert payload["metadata"]["manifest_skill_id"] == "research"
    assert payload["metadata"].get("oauth_pkce") is not True


def test_github_preset_is_remote_bearer_pat() -> None:
    payload = preset_payload("github")
    assert payload is not None
    assert payload["display_name"] == "GitHub"
    assert payload["transport"] == "streamable_http"
    assert payload["endpoint_url"] == "https://api.githubcopilot.com/mcp/"
    assert payload["auth_kind"] == "bearer"
    assert "api.githubcopilot.com" in payload["egress_hosts"]
    assert payload["metadata"]["manifest_skill_id"] == "github"
    assert payload["metadata"].get("oauth_pkce") is not True
    assert "github.com" in str(payload["metadata"].get("docs_url") or "")


def _seed_worker(con: duckdb.DuckDBPyConnection, worker_id: str) -> str:
    worker_uid = f"uid-{worker_id}"
    con.execute(
        """
        INSERT INTO main.admin_worker_catalog
          (worker_uid, tenant_id, owner_email, worker_id, display_name, source_kind, source_template_id, active)
        VALUES (?, 'default', 'owner@example.com', ?, ?, 'runtime', 'default', true)
        """,
        [worker_uid, worker_id, worker_id],
    )
    return worker_uid


def test_register_worker_mcp_connector_tools_resolves_catalog_worker_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.forge.skills.mcp_connector_bridge import register_worker_mcp_connector_tools

    tmp = Path(tempfile.mkdtemp())
    con = duckdb.connect(str(tmp / "mcp-runtime.duckdb"))
    run_pending_migrations(con)

    worker_id = "mcp-test-worker"
    worker_uid = _seed_worker(con, worker_id)
    _apply_upsert_mcp_connector(
        con,
        {
            "tenant_id": "default",
            "actor_email": "admin@test.local",
            "preset_id": "mcp_time",
            "connector_id": "",
        },
    )
    _apply_grant_worker_mcp_connector(
        con,
        {"connector_id": "mcp_mcp_time", "worker_uid": worker_uid},
    )

    mock_tool = MagicMock()
    mock_tool.name = "mcp__mcp_mcp_time__get_current_time"

    async def _fake_connect(_db: object, *, worker_uid: str, tenant_id: str = "default") -> list:
        assert worker_uid == f"uid-{worker_id}"
        return [mock_tool]

    monkeypatch.setattr(
        "duckclaw.forge.skills.mcp_connector_bridge.connect_worker_mcp_connectors",
        _fake_connect,
    )

    tools: list = []
    register_worker_mcp_connector_tools(
        tools,
        db=con,
        worker_id=worker_id,
        tenant_id="default",
    )
    assert len(tools) == 1
    assert tools[0].name == "mcp__mcp_mcp_time__get_current_time"
    con.close()


def test_factory_tool_builder_passes_worker_id_not_display_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.workers.factory_tool_builder import _build_worker_tools

    captured: dict[str, str] = {}

    def _capture(tools_list: list, *, db: object, worker_id: str, tenant_id: str = "default") -> None:
        captured["worker_id"] = worker_id
        captured["tenant_id"] = tenant_id

    monkeypatch.setattr(
        "duckclaw.forge.skills.mcp_connector_bridge.register_worker_mcp_connector_tools",
        _capture,
    )
    monkeypatch.setattr("duckclaw.workers.factory_tool_builder.load_skills", lambda _spec, _db: [])

    spec = SimpleNamespace(
        worker_id="catalog-worker-42",
        logical_worker_id="logical-42",
        name="Friendly Display Name",
        schema_name="main",
        allowed_tables=[],
        read_only=True,
        duckdb_extensions=[],
        tenant_id="default",
        worker_dir=Path("."),
    )
    db = MagicMock()
    db.query = MagicMock(return_value="[]")

    _build_worker_tools(db, spec)  # type: ignore[arg-type]

    assert captured["worker_id"] == "catalog-worker-42"
    assert captured["tenant_id"] == "default"
