"""Tests for transversal answer evidence validation."""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import ToolMessage

from duckclaw.egress.evidence_validator import bracket_citation_audit, spec_requires_bracket_citations


class _RuntimePolicy:
    def __init__(self, *capabilities: str) -> None:
        self._capabilities = set(capabilities)

    def has_capability(self, capability: str) -> bool:
        return capability in self._capabilities


def _extension_spec() -> SimpleNamespace:
    return SimpleNamespace(
        worker_id="sample-worker",
        logical_worker_id="sample-worker",
        runtime_policy=_RuntimePolicy("extension_evidence"),
    )


def test_core_skips_bracket_citation_injection() -> None:
    reply = (
        "## Impacto\n"
        "| Item | Valor |\n"
        "|------|-------|\n"
        "| A1 | $123.45 |\n"
    )
    msgs = [
        ToolMessage(
            content='{"status":"ok","symbol":"A1","rows_upserted":4}',
            name="read_sql",
            tool_call_id="1",
        ),
    ]
    assert not spec_requires_bracket_citations(_extension_spec())
    out, reason = bracket_citation_audit(reply, messages=msgs, spec=_extension_spec())
    assert reason is None
    assert out == reply
