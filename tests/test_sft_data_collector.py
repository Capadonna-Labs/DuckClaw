"""Tests for SFT DataCollector (forge/sft) — Gemma / conversation_traces."""

import json
import tempfile
from pathlib import Path

import pytest

from duckclaw.forge.sft import DataMasker, GEMMA4_TRAIN_DIR, collect_traces_to_sft
from duckclaw.forge.sft.gemma_message_flatten import flatten_messages_for_gemma


def test_datamasker_emails() -> None:
    masker = DataMasker()
    text = "Contacto: user@example.com o admin@corp.co"
    assert "[MASKED]" in masker.mask(text)
    assert "user@example.com" not in masker.mask(text)
    assert "admin@corp.co" not in masker.mask(text)


def test_datamasker_credit_cards() -> None:
    masker = DataMasker()
    text = "Tarjeta 1234-5678-9012-3456 o 1234 5678 9012 3456"
    assert "[MASKED]" in masker.mask(text)
    assert "1234-5678-9012-3456" not in masker.mask(text)


def test_default_gemma4_output_path_constant() -> None:
    assert GEMMA4_TRAIN_DIR.name == "gemma4"


def test_collect_skips_non_success() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        conv = root / "conversation_traces" / "2026" / "04" / "12"
        conv.mkdir(parents=True)
        p = conv / "traces.jsonl"
        p.write_text(
            json.dumps(
                {
                    "messages": [{"role": "user", "content": "hola"}],
                    "status": "FAILED",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        out = root / "out.jsonl"
        records, stats = collect_traces_to_sft(traces_root=root, output_path=out, require_valid_sql=False)
        assert records == []
        assert stats["skipped_non_success"] == 1
        assert stats["total_output"] == 0


def test_collect_success_messages_format() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        p = root / "t.jsonl"
        p.write_text(
            json.dumps(
                {
                    "messages": [
                        {"role": "system", "content": "Sys."},
                        {"role": "user", "content": "Hola"},
                        {"role": "assistant", "content": "Hola."},
                    ],
                    "status": "SUCCESS",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        out = root / "dataset.jsonl"
        records, stats = collect_traces_to_sft(traces_root=root, output_path=out, require_valid_sql=False)
        assert stats["total_output"] == 1
        assert "messages" in records[0]
        assert records[0]["messages"][0]["role"] == "user"
        assert "Sys." in records[0]["messages"][0]["content"]
        assert records[0]["messages"][1]["role"] == "assistant"


def test_collect_sql_invalid_skipped() -> None:
    pytest.importorskip("sqlglot")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        p = root / "t.jsonl"
        bad_sql = "SELEC * FROM x"
        p.write_text(
            json.dumps(
                {
                    "messages": [
                        {"role": "user", "content": "q"},
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "read_sql",
                                        "arguments": json.dumps({"sql": bad_sql}),
                                    },
                                }
                            ],
                        },
                    ],
                    "status": "SUCCESS",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        out = root / "out.jsonl"
        records, stats = collect_traces_to_sft(traces_root=root, output_path=out, require_valid_sql=True)
        assert records == []
        assert stats["skipped_sql"] == 1


def test_collect_sql_valid_included() -> None:
    pytest.importorskip("sqlglot")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        p = root / "t.jsonl"
        p.write_text(
            json.dumps(
                {
                    "messages": [
                        {"role": "user", "content": "q"},
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "read_sql",
                                        "arguments": json.dumps(
                                            {"sql": "SELECT 1 AS one"}
                                        ),
                                    },
                                }
                            ],
                        },
                    ],
                    "status": "SUCCESS",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        out = root / "out.jsonl"
        records, stats = collect_traces_to_sft(traces_root=root, output_path=out, require_valid_sql=True)
        assert len(records) == 1
        assert stats["skipped_sql"] == 0


def test_flatten_tool_roundtrip_alternation() -> None:
    msgs = [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "pregunta"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": "tavily_search",
                        "arguments": json.dumps({"query": "x"}),
                    },
                }
            ],
        },
        {"role": "tool", "name": "tavily_search", "content": "resultado"},
        {"role": "assistant", "content": "respuesta final"},
    ]
    flat = flatten_messages_for_gemma(msgs)
    roles = [m["role"] for m in flat]
    assert roles[0] == "user"
    assert roles == ["user", "assistant", "user", "assistant"]
    assert "[RESULTADO DE HERRAMIENTA tavily_search]" in flat[2]["content"]
    assert "[TOOL_CALLS_JSON]" in flat[1]["content"]
