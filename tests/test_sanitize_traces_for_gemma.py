"""Tests para scripts/sanitize_traces_for_gemma.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.sanitize_traces_for_gemma import (
    GemmaSanitizer,
    apply_gemma_template,
    clean_content,
    needs_evidence,
    tool_content_indicates_success,
    validate_evidence_rule,
    validate_evidence_turn,
)


def test_clean_content_strips_redacted_thinking() -> None:
    raw = "Hola <redacted_thinking>secreto\nlinea2</redacted_thinking> fin"
    assert clean_content(raw) == "Hola  fin"


def test_tool_success_json_list() -> None:
    assert tool_content_indicates_success('[{"x":1}]')


def test_tool_success_sandbox_exit_0() -> None:
    assert tool_content_indicates_success(json.dumps({"exit_code": 0, "stdout": "ok"}))


def test_tool_fail_sandbox_exit_1() -> None:
    assert not tool_content_indicates_success(json.dumps({"exit_code": 1}))


def test_tool_fail_explicit_error() -> None:
    assert not tool_content_indicates_success(json.dumps({"error": "boom"}))


def test_tool_success_fetch_market_ok() -> None:
    assert tool_content_indicates_success(json.dumps({"status": "ok", "rows_upserted": 3}))


def test_validate_evidence_rejects_cfd_without_tool() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "Temperatura: 12"},
    ]
    ok, reason = validate_evidence_rule(messages)
    assert not ok
    assert reason is not None


def test_validate_evidence_accepts_cfd_after_success_tool() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "", "tool_calls": []},
        {"role": "tool", "name": "fetch_market_data", "content": '{"status":"ok"}'},
        {"role": "assistant", "content": "Temperatura: 12 según datos."},
    ]
    ok, reason = validate_evidence_rule(messages)
    assert ok
    assert reason is None


def test_needs_evidence_false_for_negatives_even_with_currency() -> None:
    text = "No puedo ejecutar código. Mencionan USD 100 pero no verifico."
    assert not needs_evidence(text)


def test_needs_evidence_true_for_currency_without_negatives() -> None:
    assert needs_evidence("Total USD 100")


def test_validate_evidence_accepts_context_directive_without_tool() -> None:
    messages = [
        {"role": "user", "content": "SUMMARIZE_STORED_CONTEXT"},
        {"role": "assistant", "content": "Síntesis: precio USD 100 según memoria."},
    ]
    ok, reason = validate_evidence_rule(messages)
    assert ok
    assert reason is None


def test_validate_evidence_accepts_error_status_without_tool() -> None:
    messages = [
        {"role": "user", "content": "describe la db"},
        {
            "role": "assistant",
            "content": "## Error de ingesta\n\nNo pude leer tablas. Ejemplo ilustrativo COP 5000.",
        },
    ]
    ok, reason = validate_evidence_rule(messages)
    assert ok
    assert reason is None


def test_validate_evidence_accepts_figure_symmetry_without_tool() -> None:
    messages = [
        {"role": "user", "content": "Registra un gasto de 3800 COP en transporte"},
        {
            "role": "assistant",
            "content": "Listo. Monto: 3800 COP registrado en transporte.",
        },
    ]
    ok, reason = validate_evidence_rule(messages)
    assert ok
    assert reason is None


def test_validate_evidence_turn_directive_short_circuits_pattern() -> None:
    assert validate_evidence_turn(
        "PREFIX SUMMARIZE_NEW_CONTEXT SUFFIX",
        "Total $999",
        prev_was_tool=False,
    )


def test_validate_evidence_rejects_dollar_without_tool() -> None:
    messages = [
        {"role": "user", "content": "x"},
        {"role": "assistant", "content": "Total $997.58"},
    ]
    ok, _ = validate_evidence_rule(messages)
    assert not ok


def test_apply_gemma_template_includes_turn_tokens() -> None:
    messages = [
        {"role": "system", "content": "Sistema."},
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "Respuesta"},
    ]
    out = apply_gemma_template(messages)
    assert "<start_of_turn>user" in out
    assert "<start_of_turn>model" in out
    assert "<end_of_turn>" in out
    assert "Sistema." in out


def test_gemma_sanitizer_output_path_mirror(tmp_path: Path) -> None:
    inp = tmp_path / "conversation_traces" / "2026" / "01" / "01"
    inp.mkdir(parents=True)
    (inp / "traces.jsonl").write_text("", encoding="utf-8")
    san = GemmaSanitizer(
        input_root=tmp_path / "conversation_traces",
        output_root=tmp_path / "gemma4",
    )
    p = san.output_path_for(inp / "traces.jsonl")
    assert p == tmp_path / "gemma4" / "2026" / "01" / "01" / "traces.jsonl"


def test_export_keeps_line_with_evidence_ok(tmp_path: Path) -> None:
    inp = tmp_path / "conversation_traces" / "2026" / "01" / "01"
    inp.mkdir(parents=True)
    trace = {
        "messages": [
            {"role": "user", "content": "hola"},
            {"role": "tool", "name": "read_sql", "content": '[{"a":1}]'},
            {"role": "assistant", "content": "Saldo $5"},
        ],
        "session_id": "s1",
    }
    (inp / "traces.jsonl").write_text(json.dumps(trace, ensure_ascii=False) + "\n", encoding="utf-8")
    out_root = tmp_path / "gemma4"
    san = GemmaSanitizer(input_root=tmp_path / "conversation_traces", output_root=out_root)
    stats = san.export_dataset(dry_run=False)
    assert stats["lines_kept"] == 1
    out_file = out_root / "2026" / "01" / "01" / "traces.jsonl"
    assert out_file.is_file()
    line = out_file.read_text(encoding="utf-8").strip()
    row = json.loads(line)
    assert "text" in row
    assert row["session_id"] == "s1"
