"""Tests for explicit market-worker egress repair helpers."""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import HumanMessage, ToolMessage

from duckclaw.egress import market_worker_tool_repair as mod


def _tool_message(name: str, content: str) -> ToolMessage:
    return ToolMessage(content=content, name=name, tool_call_id=f"call_{name}")


def test_lone_url_with_only_clock_tool_does_not_trigger_market_repair() -> None:
    messages = [
        HumanMessage(content="https://www.infobae.com/economia/nota"),
        _tool_message(
            "get_current_time",
            '{"iso_8601":"2026-06-13T10:30:00-05:00","day_of_week":"sábado","date":"2026-06-13","time":"10:30"}',
        ),
    ]

    assert (
        mod.market_worker_needs_egress_repair(
            messages,
            "https://www.infobae.com/economia/nota",
            "",
            last_human_idx=0,
            worker_id="finanz",
            is_market_worker=True,
        )
        is False
    )


def test_empty_market_reply_after_read_sql_gets_deterministic_accounts_summary() -> None:
    messages = [
        HumanMessage(content="resumen de mis cuentas"),
        _tool_message(
            "read_sql",
            '[{"name":"Nequi","balance":1000,"currency":"COP"},{"name":"IBKR cash","balance":2.5,"currency":"USD"}]',
        ),
    ]
    spec = SimpleNamespace(worker_id="finanz", logical_worker_id="finanz")

    assert (
        mod.market_worker_needs_egress_repair(
            messages,
            "resumen de mis cuentas",
            "",
            last_human_idx=0,
            worker_id="finanz",
            is_market_worker=True,
        )
        is True
    )

    out = mod.repair_market_worker_tool_egress_reply(
        None,
        spec,
        "resumen de mis cuentas",
        "",
        messages,
        skip_llm_synthesis=True,
    )

    assert "Cuentas (2)" in out
    assert "Nequi" in out
    assert "Total:" in out
    assert "COP" in out and "USD" in out


def test_tool_label_json_echo_triggers_repair_and_uses_tool_evidence() -> None:
    messages = [
        HumanMessage(content="actualiza SPY"),
        _tool_message(
            "fetch_market_data",
            '{"status":"ok","ticker":"SPY","timeframe":"1d","rows_upserted":3,"last_close":657.25}',
        ),
    ]
    spec = SimpleNamespace(worker_id="quant_trader", logical_worker_id="quant_trader")

    assert (
        mod.market_worker_needs_egress_repair(
            messages,
            "actualiza SPY",
            'fetch_market_data: {"status":"ok","ticker":"SPY"}',
            last_human_idx=0,
            worker_id="quant_trader",
            is_market_worker=True,
        )
        is True
    )

    out = mod.repair_market_worker_tool_egress_reply(
        None,
        spec,
        "actualiza SPY",
        'fetch_market_data: {"status":"ok","ticker":"SPY"}',
        messages,
        skip_llm_synthesis=True,
    )

    assert "SPY" in out
    assert "3 velas" in out
    assert "$657.25" in out
