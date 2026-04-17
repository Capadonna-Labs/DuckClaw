"""Plantilla SIATA Analyst: manifiesto y prompts declarativos."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import requests

from duckclaw import DuckClaw
from duckclaw.workers.factory import (
    _build_worker_tools,
    _truncate_read_sql_result_for_llm,
    build_worker_graph,
)
from duckclaw.workers.loader import append_domain_closure_block, load_system_prompt
from duckclaw.workers.manifest import load_manifest


def test_siata_analyst_manifest_extensions_and_network() -> None:
    spec = load_manifest("SIATA-Analyst")
    assert spec.logical_worker_id == "siata_analyst"
    assert spec.read_only is True
    assert spec.duckdb_extensions == ["httpfs", "json"]
    assert spec.network_access is True
    assert spec.allowed_tables == []
    assert "scrape_siata_radar_realtime" in (spec.skills_list or [])
    assert getattr(spec, "openweather_config", None) is not None
    assert (spec.openweather_config or {}).get("enabled") is True


def test_siata_analyst_prompts_contain_siata_and_read_sql() -> None:
    spec = load_manifest("SIATA-Analyst")
    base = load_system_prompt(spec)
    assert "PM2.5" in base or "pm25" in base.lower()
    assert "read_sql" in base
    assert "read_json_auto" in base
    assert "LIMIT" in base
    assert "scrape_siata_radar_realtime" in base
    assert "INTERPRETACIÓN DEL RADAR" in base or "interpretación del radar" in base.lower()
    assert "nunca" in base.lower() and "##" in base
    assert "timestamp_colombia" in base
    assert "siata.gov.co" in base
    closed = append_domain_closure_block(base, spec)
    assert "SIATA" in closed
    assert "ventas" in closed.lower() or "finanzas" in closed.lower()


def test_scrape_siata_radar_skill_registered(tmp_path: Path) -> None:
    db = DuckClaw(str(tmp_path / "siata_tools.duckdb"))
    spec = load_manifest("SIATA-Analyst")
    tools = _build_worker_tools(db, spec)
    names = {t.name for t in tools}
    assert "scrape_siata_radar_realtime" in names


def test_siata_openweather_bridge_registration_called(tmp_path: Path) -> None:
    db_path = str(tmp_path / "siata_openweather_bridge.duckdb")
    db = DuckClaw(db_path)

    class _StubLLM:
        def bind_tools(self, tools: list, **_kwargs):
            return self

        def invoke(self, *_args, **_kwargs):
            return type("R", (), {"content": "ok"})()

    with patch("duckclaw.forge.skills.openweather_bridge.register_openweather_skill") as m_ow:
        build_worker_graph(
            "SIATA-Analyst",
            db_path,
            _StubLLM(),
            reuse_db=db,
            tool_surface="full",
        )
        m_ow.assert_called_once()


def _ok_response(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.raise_for_status = Mock()
    return r


@patch("requests.get")
def test_scrape_siata_radar_nested_folders(mock_get: MagicMock, tmp_path: Path) -> None:
    index_html = """
    <tr class="even"><td class="indexcolname"><a href="40/">40/</a></td></tr>
    """
    sub_html = """
    <a href="20260329/">20260329/</a>
    """
    files_html = """
    <a href="KCH_20260329_0800.png">a</a>
    <a href="KCH_20260329_0900.png">b</a>
    """
    mock_get.side_effect = [
        _ok_response(index_html),
        _ok_response(sub_html),
        _ok_response(files_html),
    ]
    db = DuckClaw(str(tmp_path / "radar_nested.duckdb"))
    spec = load_manifest("SIATA-Analyst")
    tools = _build_worker_tools(db, spec)
    tool = {t.name: t for t in tools}["scrape_siata_radar_realtime"]

    out = tool.invoke({})

    data = json.loads(out)
    assert data["status"] == "success"
    assert data["latest_folder"] == "40/20260329"
    assert data["latest_file"] == "KCH_20260329_0900.png"
    assert data["timestamp_utc"] == "09:00"
    assert data["timestamp_colombia"] == "04:00 AM"
    assert "UTC" in data["extracted_timestamp"]
    assert data["url"].endswith("KCH_20260329_0900.png")
    assert mock_get.call_count == 3


@patch("requests.get")
def test_scrape_siata_radar_compact_timestamp_filename(mock_get: MagicMock, tmp_path: Path) -> None:
    """YYYYMMDDHHMM antes de la extensión (p. ej. 202603291623.png como en producción)."""
    index_html = '<tr class="even"><td class="indexcolname"><a href="20_DBZH/">20_DBZH/</a></td></tr>'
    sub_html = '<a href="20260329/">20260329/</a>'
    files_html = '<a href="202603291623.png">r</a>'
    mock_get.side_effect = [
        _ok_response(index_html),
        _ok_response(sub_html),
        _ok_response(files_html),
    ]
    db = DuckClaw(str(tmp_path / "radar_compact.duckdb"))
    spec = load_manifest("SIATA-Analyst")
    tools = _build_worker_tools(db, spec)
    tool = {t.name: t for t in tools}["scrape_siata_radar_realtime"]
    out = tool.invoke({})
    data = json.loads(out)
    assert data["status"] == "success"
    assert data["latest_file"] == "202603291623.png"
    assert data["timestamp_utc"] == "16:23"
    assert data["timestamp_colombia"] == "11:23 AM"


@patch("requests.get")
def test_scrape_siata_radar_date_at_root(mock_get: MagicMock, tmp_path: Path) -> None:
    index_html = """
    <a href="20260329/">d2</a>
    """
    files_html = """<a href="last_20260329_1800.json">j</a>"""
    mock_get.side_effect = [_ok_response(index_html), _ok_response(files_html)]

    db = DuckClaw(str(tmp_path / "radar_root.duckdb"))
    spec = load_manifest("SIATA-Analyst")
    tools = _build_worker_tools(db, spec)
    tool = {t.name: t for t in tools}["scrape_siata_radar_realtime"]
    out = tool.invoke({})
    data = json.loads(out)
    assert data["status"] == "success"
    assert data["latest_folder"] == "20260329"
    assert data["latest_file"] == "last_20260329_1800.json"
    assert data["timestamp_utc"] == "18:00"
    assert data["timestamp_colombia"] == "01:00 PM"
    assert mock_get.call_count == 2


@patch("requests.get")
def test_scrape_siata_radar_connection_error(mock_get: MagicMock, tmp_path: Path) -> None:
    mock_get.side_effect = requests.exceptions.ConnectionError("refused")
    db = DuckClaw(str(tmp_path / "radar_err.duckdb"))
    spec = load_manifest("SIATA-Analyst")
    tools = _build_worker_tools(db, spec)
    tool = {t.name: t for t in tools}["scrape_siata_radar_realtime"]
    out = tool.invoke({})
    data = json.loads(out)
    assert data["status"] == "error"
    assert "error" in data


def test_siata_read_json_requires_limit(tmp_path: Path) -> None:
    db = DuckClaw(str(tmp_path / "siata_limit.duckdb"))
    spec = load_manifest("SIATA-Analyst")
    tools = _build_worker_tools(db, spec)
    by_name = {t.name: t for t in tools}
    bad = by_name["read_sql"].invoke({"query": "SELECT * FROM read_json_auto('https://example.com/x.json')"})
    parsed = json.loads(bad)
    assert "error" in parsed
    assert "LIMIT" in parsed["error"]
    ok_limit = by_name["read_sql"].invoke(
        {"query": "SELECT * FROM read_json_auto('https://example.com/x.json') LIMIT 1"}
    )
    parsed_ok = json.loads(ok_limit)
    if isinstance(parsed_ok, dict) and "error" in parsed_ok:
        assert "Incluye LIMIT" not in parsed_ok["error"]


def test_truncate_read_sql_result_for_llm_wraps_large_output() -> None:
    huge = "x" * 90_000
    out = _truncate_read_sql_result_for_llm(huge)
    data = json.loads(out)
    assert data.get("warning")
    assert "truncada" in data["warning"].lower() or "truncad" in data["warning"].lower()
    assert data.get("total_chars") == len(huge)
    assert isinstance(data.get("preview"), str)
    assert len(data["preview"]) < len(huge)


def test_truncate_read_sql_result_for_llm_passes_through_small() -> None:
    small = '[{"a": 1}]'
    assert _truncate_read_sql_result_for_llm(small) == small
