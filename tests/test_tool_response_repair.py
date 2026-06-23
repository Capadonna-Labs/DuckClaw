"""Contracts for transversal tool-response egress repair."""

from __future__ import annotations

import importlib.util
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import HumanMessage, ToolMessage


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL_RESPONSE_REPAIR_PATH = (
    REPO_ROOT
    / "packages"
    / "agents"
    / "src"
    / "duckclaw"
    / "egress"
    / "tool_response_repair.py"
)


def _tool_message(name: str, content: str) -> ToolMessage:
    return ToolMessage(content=content, name=name, tool_call_id=f"call_{name}")


def _repair_module():
    spec = importlib.util.find_spec("duckclaw.egress.tool_response_repair")
    assert spec is not None
    return import_module("duckclaw.egress.tool_response_repair")


def test_market_worker_tool_repair_is_not_the_canonical_owner() -> None:
    assert importlib.util.find_spec("duckclaw.egress.market_worker_tool_repair") is None


def test_tool_response_repair_has_no_domain_vertical_markers() -> None:
    assert TOOL_RESPONSE_REPAIR_PATH.exists()
    text = TOOL_RESPONSE_REPAIR_PATH.read_text(encoding="utf-8").lower()

    forbidden = (
        "market_worker_tool_repair",
        "market",
        "quant",
        "platform-orchestrator",
        "finance",
        "trader",
        "pqrsd",
        "pqrs",
        "leila",
        "war_room",
        "wr_",
    )

    assert [marker for marker in forbidden if marker in text] == []


def test_lone_url_with_only_clock_tool_does_not_trigger_response_repair() -> None:
    mod = _repair_module()
    messages = [
        HumanMessage(content="https://www.example.com/story"),
        _tool_message(
            "get_current_time",
            '{"iso_8601":"2026-06-13T10:30:00-05:00","day_of_week":"sabado","date":"2026-06-13","time":"10:30"}',
        ),
    ]

    assert (
        mod.tool_response_needs_egress_repair(
            messages,
            "https://www.example.com/story",
            "",
            last_human_idx=0,
            repair_enabled=True,
        )
        is False
    )


def test_empty_reply_after_read_sql_gets_generic_tool_summary() -> None:
    mod = _repair_module()
    messages = [
        HumanMessage(content="resume mis filas"),
        _tool_message(
            "read_sql",
            '[{"name":"Alpha","balance":1000,"currency":"USD"},{"name":"Beta","balance":2.5,"currency":"EUR"}]',
        ),
    ]
    spec = SimpleNamespace(worker_id="worker_alpha", logical_worker_id="worker_alpha")

    assert (
        mod.tool_response_needs_egress_repair(
            messages,
            "resume mis filas",
            "",
            last_human_idx=0,
            repair_enabled=True,
        )
        is True
    )

    out = mod.repair_tool_response_egress_reply(
        None,
        spec,
        "resume mis filas",
        "",
        messages,
        skip_llm_synthesis=True,
    )

    assert "2 registros" in out.lower() or "registro" in out.lower()
    assert "Cuentas" not in out
    assert "Deudas" not in out


def test_tool_label_json_echo_triggers_repair_and_uses_tool_evidence() -> None:
    mod = _repair_module()
    messages = [
        HumanMessage(content="actualiza datos"),
        _tool_message(
            "fetch_external_data",
            '{"status":"ok","item":"SPY","rows_upserted":3,"last_value":657.25}',
        ),
    ]
    spec = SimpleNamespace(worker_id="worker_beta", logical_worker_id="worker_beta")

    assert (
        mod.tool_response_needs_egress_repair(
            messages,
            "actualiza datos",
            'fetch_external_data: {"status":"ok","item":"SPY"}',
            last_human_idx=0,
            repair_enabled=True,
        )
        is True
    )

    out = mod.repair_tool_response_egress_reply(
        None,
        spec,
        "actualiza datos",
        'fetch_external_data: {"status":"ok","item":"SPY"}',
        messages,
        skip_llm_synthesis=True,
    )

    assert "Operación completada" in out or "SPY" in out
    assert "fetch_external_data:" not in out
