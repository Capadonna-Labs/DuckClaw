"""Guardrails for removed domain-specific state-delta handlers."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def test_domain_state_delta_handler_is_not_core_db_writer() -> None:
    writer = _REPO / "services" / "db-writer"

    assert not (writer / "quant_state_delta_handler.py").exists()
    assert not (writer / "models" / "quant_state_delta.py").exists()


def test_db_writer_main_does_not_import_domain_state_delta_handler() -> None:
    main_source = (_REPO / "services" / "db-writer" / "main.py").read_text(encoding="utf-8")

    assert "quant_state_delta_handler" not in main_source
