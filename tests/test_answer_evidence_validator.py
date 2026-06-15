"""Tests for transversal answer evidence validation."""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import ToolMessage

from duckclaw.egress.evidence_validator import bracket_citation_audit


class _RuntimePolicy:
    def __init__(self, *capabilities: str) -> None:
        self._capabilities = set(capabilities)

    def has_capability(self, capability: str) -> bool:
        return capability in self._capabilities


def _market_spec() -> SimpleNamespace:
    return SimpleNamespace(
        worker_id="market-worker",
        logical_worker_id="market-worker",
        runtime_policy=_RuntimePolicy("market_analysis"),
    )


def test_injects_brackets_into_market_table_row() -> None:
    reply = (
        "## Impacto\n"
        "| Ticker | Precio |\n"
        "|--------|--------|\n"
        "| NVDA | $123.45 |\n"
        "| AVGO | $456.78 |\n"
    )
    msgs = [
        ToolMessage(
            content='{"status":"ok","ticker":"NVDA","rows_upserted":4}',
            name="fetch_market_data",
            tool_call_id="1",
        ),
        ToolMessage(
            content='{"status":"ok","ticker":"AVGO","rows_upserted":4}',
            name="fetch_market_data",
            tool_call_id="2",
        ),
    ]
    out, reason = bracket_citation_audit(reply, messages=msgs, spec=_market_spec())
    assert reason
    assert "[fetch_market_data/NVDA]" in out
    assert "[fetch_market_data/AVGO]" in out


def test_skips_when_brackets_already_present() -> None:
    reply = "NVDA $123.45 [fetch_market_data/NVDA]"
    msgs = [
        ToolMessage(
            content='{"status":"ok","ticker":"NVDA"}',
            name="fetch_market_data",
            tool_call_id="1",
        ),
    ]
    out, reason = bracket_citation_audit(reply, messages=msgs, spec=_market_spec())
    assert reason is None
    assert out == reply
